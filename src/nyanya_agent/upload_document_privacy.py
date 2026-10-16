"""Bounded, local-only document extraction and personal-information patterns.

No network, subprocess, OCR or filesystem extraction is performed. A clean
report means only that known patterns were not found in supported text; it is
not proof that a document has no personal data. Names/addresses/accounts/passports
are label-based. Images, uncertain package parts and unsupported rendering are
held. Source code is inspected as text, never executed or rendered. Counts are
unique normalized matches per kind; values never leave in reports or errors.
"""

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import io
import json
from pathlib import PurePosixPath
import posixpath
import re
import stat
import struct
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
import zlib

from nyanya_agent.task_outcomes import SafeOperationError


MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
MAX_ZIP_ENTRIES = 256
MAX_XML_PART_BYTES = 4 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 16 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
MAX_XML_NODES = 50_000
MAX_XML_DEPTH = 64
MAX_INSPECTION_CHARS = 64 * 1024 * 1024
MAX_FINDINGS_PER_KIND = 10_000
MAX_INSPECTION_SECONDS = 10.0  # Cooperative budget, checked before/after bounded units.
_TEXT_SUFFIXES = frozenset({
    "", ".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".xml", ".html", ".htm", ".css", ".js", ".ts",
    ".jsx", ".tsx", ".py", ".sh", ".sql", ".r",
})
_OFFICE_MAIN = {
    ".docx": ("word/document.xml", "document"),
    ".xlsx": ("xl/workbook.xml", "workbook"),
    ".pptx": ("ppt/presentation.xml", "presentation"),
}
_BINARY_HEADERS = (
    b"%PDF-", b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b",
    b"\x7fELF", b"MZ", b"\x89PNG", b"\xff\xd8\xff", b"GIF87a", b"GIF89a",
    b"II*\0", b"MM\0*", b"RIFF", b"Rar!", b"7z\xbc\xaf\x27\x1c", b"BZh",
    b"\xfd7zXZ\0", bytes.fromhex("d0cf11e0a1b11ae1"), b"SQLite format 3\0",
)
_CREDENTIAL_TAG = re.compile(
    r"(?i)(?:password|passwd|api[_-]?key|token|secret|credential|private[_-]?key|authorization|cookie)"
)
_VISUAL_XML_TAGS = frozenset({
    "svg", "image", "img", "blip", "imagedata", "oleobject", "object", "altchunk",
    "pict", "picture", "pic", "graphic", "graphicdata", "drawing", "shape", "canvas",
    "video", "audio", "embed", "iframe", "script", "include",
})
_VISUAL_HTML_TAGS = frozenset({
    "img", "image", "svg", "object", "embed", "iframe", "canvas", "picture", "source",
    "video", "audio", "script", "link", "math",
})
_RENDERED_REFERENCE = re.compile(
    r"(?i)<\s*(?:img|image|svg|object|embed|iframe|canvas|picture|video|audio|script|link)\b"
    r"|data\s*:\s*image/|\burl\s*\("
)
_PATTERNS = {
    "email": re.compile(r"(?i)(?<![\w@])([a-z0-9._%+\-]{1,64}@[a-z0-9.\-]{1,253}\.[a-z]{2,24})(?![\w@])"),
    "phone": re.compile(
        r"(?<!\d)((?:\+82[ \-]?(?:0)?1[016789]|01[016789])[ \-]?\d{3,4}[ \-]?\d{4})(?!\d)"
    ),
    "resident_id": re.compile(r"(?<!\d)(\d{6}[ \-]?[1-8]\d{6})(?!\d)"),
    "payment_card": re.compile(r"(?<!\d)((?:\d[ \-]?){12,18}\d)(?!\d)"),
    "bank_account": re.compile(
        r"(?i)(?:계좌(?:번호)?|bank[ _-]?account|account[ _-]?(?:number|no\.?))[\"']?\s*[:=]\s*[\"']?([0-9][0-9 \-]{5,32}[0-9])"
    ),
    "passport": re.compile(r"(?i)(?:여권(?:번호)?|passport(?:[ _-]?(?:number|no\.?))?)[\"']?\s*[:=]\s*[\"']?([a-z0-9]{6,12})"),
    "person_name": re.compile(r"(?im)(?<![\w])(?:성명|이름|(?:full[ _-]?)?name|creator|lastModifiedBy)[\"']?\s*[:=]\s*[\"']?([^\r\n<>;]{2,100})"),
    "address": re.compile(r"(?im)(?<![\w])(?:주소|(?:postal[ _-]?|street[ _-]?)?address)[\"']?\s*[:=]\s*[\"']?([^\r\n<>;]{5,200})"),
    "local_path": re.compile(r"(?i)((?:/(?:Users|home)/[^\s/<>\"']+|[a-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s<>\"']+|~[\\/][^\s<>\"']+))"),
}


@dataclass(frozen=True)
class PrivacyReport:
    counts: dict[str, int]

    @property
    def requires_confirmation(self) -> bool:
        return bool(self.counts)


def _blocked(reason):
    # This exception may be shown directly: never append parser output, paths,
    # matched values, filenames, URLs or document text.
    raise SafeOperationError("Document inspection held: " + reason)


class _Budget:
    def __init__(self):
        self.deadline = time.monotonic() + MAX_INSPECTION_SECONDS
        self.chars = 0

    def check(self):
        if time.monotonic() > self.deadline:
            _blocked("inspection time bound")

    def consume(self, text):
        self.check()
        self.chars += len(text)
        if self.chars > MAX_INSPECTION_CHARS:
            _blocked("inspection text bound")


def _decode(data, *, xml=False):
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = data.decode("utf-16")
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeError:
                if xml:
                    _blocked("unsupported XML encoding")
                text = data.decode("cp949")
    except UnicodeError:
        _blocked("unsupported text encoding")
    if any(ord(char) < 32 and char not in "\t\n\r\f" for char in text):
        _blocked("binary or unsupported text content")
    return text


def _normalized(text):
    text = unicodedata.normalize("NFKC", text)
    return "".join(char for char in text if unicodedata.category(char) != "Cf")


def _luhn(value):
    digits = re.sub(r"\D", "", value)
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        digit = int(char)
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


class _BoundedTreeBuilder(ET.TreeBuilder):
    def __init__(self, budget):
        super().__init__(insert_comments=True, insert_pis=True)
        self.nodes = 0
        self.depth = 0
        self.budget = budget

    def start(self, tag, attrs):
        self.nodes += 1
        self.depth += 1
        self.budget.check()
        if self.nodes > MAX_XML_NODES or self.depth > MAX_XML_DEPTH:
            _blocked("XML resource bound")
        return super().start(tag, attrs)

    def end(self, tag):
        element = super().end(tag)
        self.depth -= 1
        return element

    def comment(self, text):
        self.nodes += 1
        self.budget.check()
        if self.nodes > MAX_XML_NODES:
            _blocked("XML resource bound")
        return super().comment(text)

    def pi(self, target, text=None):
        self.nodes += 1
        self.budget.check()
        if self.nodes > MAX_XML_NODES:
            _blocked("XML resource bound")
        return super().pi(target, text)


def _local_name(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _parse_xml(data, budget):
    if len(data) > MAX_XML_PART_BYTES:
        _blocked("XML part byte bound")
    text = _decode(data, xml=True)
    folded = text.casefold()
    if "<!doctype" in folded or "<!entity" in folded:
        _blocked("XML declarations are unsupported")
    try:
        parser = ET.XMLParser(target=_BoundedTreeBuilder(budget))
        root = ET.fromstring(text, parser=parser)
    except SafeOperationError:
        raise
    except (ET.ParseError, ValueError, LookupError, RecursionError):
        _blocked("XML extraction failed")
    budget.check()
    return text, root


def _xml_views(raw, root, budget):
    texts = []
    labels = []
    yield raw
    for item in root.iter():
        budget.check()
        label = _local_name(item.tag)
        if "encrypt" in label.casefold():
            _blocked("encrypted XML content is uninspected")
        if label.casefold() in _VISUAL_XML_TAGS:
            _blocked("XML visual or embedded content is uninspected")
        if item.text:
            texts.append(item.text)
            if label:
                labels.append(label + ": " + item.text)
        if item.tail:
            texts.append(item.tail)
        attribute_names = [_local_name(key).casefold() for key in item.attrib]
        if len(attribute_names) != len(set(attribute_names)):
            _blocked("ambiguous XML attributes are uninspected")
        values = {_local_name(key): value for key, value in item.attrib.items()}
        for key, value in values.items():
            yield value
            yield key + ": " + value
        if label and _CREDENTIAL_TAG.search(label):
            yield json.dumps({label: "".join(item.itertext()).strip()}, ensure_ascii=False)
        for key, label_value in values.items():
            if key.casefold() in {"name", "key"} and _CREDENTIAL_TAG.search(label_value):
                value = values.get("value", "".join(item.itertext()).strip())
                yield json.dumps({label_value: value}, ensure_ascii=False)
    yield "\n".join(labels)
    yield "".join(texts)
    yield "".join(text.strip() for text in texts)
    yield " ".join(texts)


def _covered_zip(data, archive, end, central_offset, central_size, entries, budget):
    """Accept contiguous classic ZIP records only; no overlooked byte ranges."""
    members = archive.infolist()
    if entries != len(members) or not 1 <= entries <= MAX_ZIP_ENTRIES:
        _blocked("Office part count bound")
    if central_offset + central_size != end or archive.start_dir != central_offset:
        _blocked("uninspected Office directory content")
    cursor = central_offset
    for info in members:
        budget.check()
        if cursor + 46 > end or data[cursor:cursor + 4] != b"PK\x01\x02":
            _blocked("Office central directory mismatch")
        name_length, extra_length, comment_length = struct.unpack_from("<HHH", data, cursor + 28)
        disk = struct.unpack_from("<H", data, cursor + 34)[0]
        offset = struct.unpack_from("<I", data, cursor + 42)[0]
        if disk or extra_length or offset != info.header_offset:
            _blocked("unsupported Office directory metadata")
        cursor += 46 + name_length + extra_length + comment_length
        if cursor > end:
            _blocked("Office central directory bound")
    if cursor != end:
        _blocked("uninspected Office central directory gap")
    cursor = 0
    ranges = {}
    for info in sorted(members, key=lambda item: item.header_offset):
        budget.check()
        offset = info.header_offset
        if offset != cursor or offset + 30 > central_offset or data[offset:offset + 4] != b"PK\x03\x04":
            _blocked("uninspected Office local record gap")
        flags, method = struct.unpack_from("<HH", data, offset + 6)
        crc, compressed, uncompressed = struct.unpack_from("<III", data, offset + 14)
        name_length, extra_length = struct.unpack_from("<HH", data, offset + 26)
        if (
            flags & ~(0x800 | 0x6) or flags != info.flag_bits or method != info.compress_type
            or extra_length or compressed != info.compress_size or uncompressed != info.file_size
            or crc != info.CRC
        ):
            _blocked("unsupported Office local metadata or data descriptor")
        start = offset + 30 + name_length
        stop = start + compressed
        if stop > central_offset:
            _blocked("Office local record byte bound")
        local_name = data[offset + 30:start].decode("utf-8" if flags & 0x800 else "cp437")
        if local_name != info.orig_filename:
            _blocked("Office local filename mismatch")
        ranges[info.filename] = (start, stop)
        cursor = stop
    if cursor != central_offset:
        _blocked("uninspected Office local directory gap")
    return members, ranges


def _read_zip_xml(data, info, byte_range, budget):
    start, stop = byte_range
    compressed = data[start:stop]
    if info.compress_type == zipfile.ZIP_STORED:
        content = compressed
    else:
        inflater = zlib.decompressobj(-15)
        content = inflater.decompress(compressed, MAX_XML_PART_BYTES + 1)
        if inflater.unconsumed_tail or not inflater.eof or inflater.unused_data:
            _blocked("uninspected Office compressed-stream content")
    budget.check()
    if len(content) != info.file_size or len(content) > MAX_XML_PART_BYTES or zlib.crc32(content) != info.CRC:
        _blocked("Office part byte or integrity bound")
    return content


def _office_views(data, suffix, budget):
    if not data.startswith(b"PK\x03\x04"):
        _blocked("Office extraction failed or encrypted document")
    end = data.rfind(b"PK\x05\x06")
    if end < 0 or end + 22 > len(data):
        _blocked("Office extraction failed")
    disk, central_disk, disk_entries, entries, central_size, central_offset, comment_length = struct.unpack_from("<HHHHIIH", data, end + 4)
    if disk or central_disk or disk_entries != entries or end + 22 + comment_length != len(data):
        _blocked("uninspected Office trailing or multidisk content")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members, ranges = _covered_zip(data, archive, end, central_offset, central_size, entries, budget)
        seen = set()
        names = set()
        total = 0
        for info in members:
            budget.check()
            name = info.orig_filename
            path = PurePosixPath(name)
            folded = name.casefold()
            if (
                not name or len(name) > 512 or "\0" in name or "\\" in name or ":" in name
                or path.is_absolute() or ".." in path.parts or len(path.parts) > 32
                or folded in seen or path.as_posix() != name.rstrip("/")
            ):
                _blocked("unsupported Office member path")
            seen.add(folded)
            names.add(name)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or info.flag_bits & 1:
                _blocked("encrypted or linked Office part")
            if info.extra or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                _blocked("unsupported Office part metadata or compression")
            if any(part in {"media", "embeddings", "activex"} or part.startswith(("thumbnail", "vbaproject")) for part in (component.casefold() for component in path.parts)):
                _blocked("Office media or embedded path is uninspected")
            if info.is_dir():
                if info.file_size or info.compress_size or info.CRC or info.compress_type != zipfile.ZIP_STORED:
                    _blocked("unsupported Office directory content")
                continue
            if not (folded.endswith(".xml") or folded.endswith(".rels")):
                _blocked("Office media or binary part requires unavailable inspection")
            if info.file_size > MAX_XML_PART_BYTES:
                _blocked("Office part byte bound")
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES or info.file_size > max(info.compress_size, 1) * MAX_COMPRESSION_RATIO:
                _blocked("Office decompression bound")
        main, expected_root = _OFFICE_MAIN[suffix]
        if not {"[Content_Types].xml", "_rels/.rels", main} <= names:
            _blocked("required Office structure missing")
        yield _decode(archive.comment)
        for info in members:
            yield info.orig_filename
            yield _decode(info.comment)
            if info.is_dir():
                continue
            raw, root = _parse_xml(_read_zip_xml(data, info, ranges[info.filename], budget), budget)
            if info.filename == main and _local_name(root.tag) != expected_root:
                _blocked("Office main part mismatch")
            if info.filename == "[Content_Types].xml":
                if _local_name(root.tag) != "Types":
                    _blocked("Office content types mismatch")
                for item in root.iter():
                    content_type = item.attrib.get("ContentType", "").casefold()
                    if content_type and (
                        not (content_type in {"application/xml", "text/xml"} or content_type.endswith("+xml"))
                        or content_type.startswith(("image/", "font/"))
                        or any(word in content_type for word in ("vba", "oleobject", "macroenabled", "activex", "encrypt", "obfuscatedfont"))
                    ):
                        _blocked("Office content type requires unavailable inspection")
            if info.filename.casefold().endswith(".rels"):
                if _local_name(root.tag) != "Relationships":
                    _blocked("Office relationship extraction failed")
                prefix = info.filename.rsplit("/_rels/", 1)[0] if "/_rels/" in info.filename else ""
                for item in root.iter():
                    if _local_name(item.tag) != "Relationship":
                        continue
                    target = item.attrib.get("Target", "")
                    if item.attrib.get("TargetMode", "Internal").casefold() != "internal" or re.match(r"[a-z][a-z0-9+.-]*:", target, re.I):
                        _blocked("external Office content is uninspected")
                    target_path = posixpath.normpath(posixpath.join(prefix, target.split("#", 1)[0]))
                    if "\\" in target or target_path.startswith("../") or target_path not in names:
                        _blocked("unavailable Office relationship target")
            yield from _xml_views(raw, root, budget)


class _HTMLViews(HTMLParser):
    def __init__(self, budget):
        super().__init__(convert_charrefs=True)
        self.budget = budget
        self.parts = []
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        self.budget.check()
        if self.nodes > MAX_XML_NODES:
            _blocked("HTML resource bound")
        if tag.casefold().split(":")[-1] in _VISUAL_HTML_TAGS:
            _blocked("HTML visual or external content is uninspected")
        attribute_names = [key.casefold() for key, _value in attrs]
        if len(attribute_names) != len(set(attribute_names)):
            _blocked("ambiguous HTML attributes are uninspected")
        values = {key: value for key, value in attrs if value is not None}
        for key, value in values.items():
            self.parts.extend((value, key + ": " + value))
        for key in ("name", "type", "id"):
            if _CREDENTIAL_TAG.search(values.get(key, "")):
                self.parts.append(json.dumps({values[key]: values.get("value", "")}, ensure_ascii=False))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        self.budget.check()
        if _RENDERED_REFERENCE.search(data):
            _blocked("HTML visual or external content is uninspected")
        self.parts.append(data)

    def handle_comment(self, data):
        self.handle_data(unescape(data))


def _json_views(text, suffix, budget):
    lines = text.splitlines() if suffix == ".jsonl" else [text]
    nodes = 0
    for line in lines:
        if suffix == ".jsonl" and not line.strip():
            continue
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    _blocked("ambiguous JSON keys are uninspected")
                result[key] = value
            return result
        parsed = json.loads(line, object_pairs_hook=unique_object)
        pending = [(parsed, 0)]
        while pending:
            budget.check()
            value, depth = pending.pop()
            nodes += 1
            if nodes > MAX_XML_NODES or depth > MAX_XML_DEPTH:
                _blocked("JSON resource bound")
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    if not isinstance(item, (dict, list)):
                        yield key + ": " + str(item)
                    pending.append((item, depth + 1))
            elif isinstance(value, list):
                pending.extend((item, depth + 1) for item in value)
            else:
                yield str(value)


def _text_views(data, suffix, budget):
    if data.lstrip().startswith(_BINARY_HEADERS):
        _blocked("binary content requires unavailable inspection")
    text = _decode(data)
    if suffix in {".html", ".htm", ".xml", ".md", ".rst"}:
        if _RENDERED_REFERENCE.search(text) or (
            suffix == ".md" and re.search(r"!\[[^\]\r\n]{0,500}\]", text)
        ) or (
            suffix == ".rst" and re.search(r"(?im)^\s*\.\.\s+(?:\|[^|\r\n]{1,200}\|\s*)?(?:image|figure)::", text)
        ):
            _blocked("document visual or external content requires unavailable inspection")
    yield text
    if suffix == ".xml":
        raw, root = _parse_xml(data, budget)
        yield from _xml_views(raw, root, budget)
    elif suffix in {".html", ".htm"}:
        restored = unescape(text)
        yield restored
        parser = _HTMLViews(budget)
        parser.feed(text)
        parser.close()
        yield from parser.parts
        yield "".join(parser.parts)
        yield "".join(part.strip() for part in parser.parts)
    elif suffix in {".json", ".jsonl"}:
        yield from _json_views(text, suffix, budget)


def inspect_document(data: bytes, filename: str) -> PrivacyReport:
    """Inspect frozen bytes; return counts only or a fixed fail-closed diagnostic.

    Supported: explicit text suffixes (UTF-8, BOM UTF-16, strict CP949), bounded
    structured views and text-only classic DOCX/XLSX/PPTX XML packages. PDF,
    image/OCR, legacy Office, archives, executables and unknown formats are held.
    No optional parser is silently installed or called. Authentication findings
    cannot be confirmed. Classic ZIP data descriptors/extra fields are held.
    """
    if not isinstance(data, bytes) or not isinstance(filename, str) or len(filename) > 512:
        _blocked("invalid inspection input")
    if len(data) > MAX_DOCUMENT_BYTES:
        _blocked("document byte bound")
    suffix = PurePosixPath(filename).suffix.casefold()
    matches = {kind: set() for kind in _PATTERNS}
    budget = _Budget()
    # Lazy import prevents a cycle with the descriptor upload boundary.
    from nyanya_agent.context_security import sensitive_content

    def inspect(text):
        budget.consume(text)
        text = _normalized(text)
        try:
            credentials = sensitive_content(text)
        except (ValueError, TypeError, RecursionError):
            _blocked("credential inspection could not complete")
        budget.check()
        if credentials:
            _blocked("authentication material is blocked")
        for kind, pattern in _PATTERNS.items():
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                if kind == "payment_card" and not _luhn(value):
                    continue
                canonical = re.sub(r"\D", "", value) if kind in {"phone", "resident_id", "payment_card", "bank_account"} else value.casefold()
                matches[kind].add(canonical)
                if len(matches[kind]) > MAX_FINDINGS_PER_KIND:
                    _blocked("personal information count bound")
            budget.check()

    try:
        inspect(filename)
        if suffix in _OFFICE_MAIN:
            for text in _office_views(data, suffix, budget):
                inspect(text)
        elif suffix in _TEXT_SUFFIXES:
            for text in _text_views(data, suffix, budget):
                inspect(text)
        elif suffix == ".pdf":
            _blocked("PDF extraction is unavailable")
        else:
            _blocked("unsupported format or image inspection unavailable")
        budget.check()
    except SafeOperationError:
        raise
    except (OSError, ValueError, TypeError, LookupError, RuntimeError, EOFError, OverflowError,
            struct.error, RecursionError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error):
        _blocked("document extraction could not complete")
    return PrivacyReport({kind: len(values) for kind, values in matches.items() if values})
