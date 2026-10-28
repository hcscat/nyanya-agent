"""Synthetic document privacy regressions: no real documents, network or parsers."""
import io
import json
import struct
import zipfile
from xml.sax.saxutils import escape
import pytest
from nyanya_agent.task_outcomes import SafeOperationError
from nyanya_agent.upload_document_privacy import inspect_document
EMAIL = 'fixture.person@example.invalid'
PHONE = '010-0000-0000'
MAIN_PARTS = {'.docx': ('word/document.xml', 'document'), '.xlsx': ('xl/workbook.xml', 'workbook'), '.pptx': ('ppt/presentation.xml', 'presentation')}

def office_document(suffix='.docx', text='Synthetic public document', *, parts=None, archive_comment=b'', member_comment=b'', body_xml=None):
    """Create a text-only OOXML-shaped fixture entirely in memory."""
    main, root = MAIN_PARTS[suffix]
    body = body_xml if body_xml is not None else f'<t>{escape(text)}</t>'
    members = {'[Content_Types].xml': f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/{main}" ContentType="application/xml"/></Types>'.encode(), '_rels/.rels': f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{main}"/></Relationships>'.encode(), main: f'<{root}>{body}</{root}>'.encode()}
    members.update(parts or {})
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.comment = archive_comment
        for name, value in members.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.comment = member_comment if name == main else b''
            archive.writestr(info, value)
    return output.getvalue()

def assert_blocked(data, name, *hidden):
    with pytest.raises(SafeOperationError) as caught:
        inspect_document(data, name)
    diagnostic = str(caught.value)
    assert diagnostic
    for value in hidden:
        assert value not in diagnostic

@pytest.mark.parametrize('suffix', ['.txt', '.md', '.csv', '.json', '.py', ''])
def test_clean_supported_text_has_no_confirmation(suffix):
    content = b'{"description": "Synthetic public project description."}' if suffix == '.json' else b'Synthetic public project description.'
    report = inspect_document(content, 'document' + suffix)
    assert report.counts == {}
    assert report.requires_confirmation is False

@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16', 'cp949'])
def test_explicit_supported_text_encodings_are_actually_scanned(encoding):
    report = inspect_document(('합성 연락처: ' + EMAIL).encode(encoding), 'document.txt')
    assert report.counts['email'] == 1
    assert report.requires_confirmation is True
    assert EMAIL not in repr(report)

@pytest.mark.parametrize(('content', 'kind'), [(EMAIL, 'email'), (PHONE, 'phone'), ('연락처 +82 10 0000 0000', 'phone'), ('주민등록번호: 900101-1000000', 'resident_id'), ('카드번호: ' + '4111' + '1111' * 3, 'payment_card'), ('계좌번호: 000-123456-00', 'bank_account'), ('여권번호: M00000000', 'passport'), ('성명: 가나다', 'person_name'), ('Name: Synthetic Person', 'person_name'), ('주소: 서울특별시 합성구 예시로 0', 'address'), ('Address: 0 Synthetic Example Road', 'address'), ('/Users/' + 'synthetic-owner/document.txt', 'local_path'), ('C:\\Users\\synthetic-owner\\document.txt', 'local_path'), ('~/synthetic/document.txt', 'local_path')])
def test_personal_information_returns_kind_and_count_only(content, kind):
    report = inspect_document(content.encode(), 'document.txt')
    assert report.requires_confirmation
    assert report.counts[kind] >= 1
    assert all((isinstance(key, str) and isinstance(value, int) and (value > 0) for key, value in report.counts.items()))
    assert content not in repr(report)
    assert content not in json.dumps(report.counts)

def test_card_detection_uses_luhn_instead_of_any_sixteen_digit_number():
    report = inspect_document(b'Counter: 1111111111111112', 'document.txt')
    assert 'payment_card' not in report.counts

def test_known_pattern_counts_do_not_retain_detected_values():
    report = inspect_document((EMAIL + ' ' + EMAIL).encode(), 'document.txt')
    assert report.counts['email'] == 1
    assert not any((EMAIL in str(value) for value in vars(report).values()))

def test_compatibility_normalization_does_not_hide_email():
    content = 'ｆｉｘｔｕｒｅ＠ｅｘａｍｐｌｅ．ｉｎｖａｌｉｄ'
    report = inspect_document(content.encode(), 'document.txt')
    assert report.counts['email'] == 1

@pytest.mark.parametrize('content', ['password: synthetic-authentication-value', 'TOKEN=synthetic-authentication-value', 'Authorization: Bearer synthetic-authentication-value', '-----BEGIN PRIVATE KEY-----\nsynthetic\n-----END PRIVATE KEY-----', 'api_key=' + 'sk-' + 'SYNTHETIC0000000000' * 2])
def test_credentials_are_hard_blocked_before_privacy_confirmation(content):
    assert_blocked((EMAIL + '\n' + content).encode(), 'document.txt', EMAIL, 'synthetic-authentication-value', 'SYNTHETIC0000000000')

def test_blank_credential_example_and_file_reference_are_not_embedded_credentials():
    report = inspect_document(b'TOKEN=\nTOKEN_FILE=data/example.token\n', 'document.txt')
    assert not report.requires_confirmation

@pytest.mark.parametrize(('data', 'filename'), [(b'%PDF-1.7\nsynthetic text', 'document.pdf'), (b'Synthetic textual placeholder', 'document.pdf'), (b'%PDF-1.7\nsynthetic text', 'document.txt'), (b'\x89PNG\r\n\x1a\n', 'scan.png'), (b'\xff\xd8\xffsynthetic', 'scan.jpg'), (b'Synthetic textual placeholder', 'scan.png'), (b'GIF89asynthetic', 'scan.gif'), (b'PK\x03\x04synthetic', 'archive.zip'), (b'\x1f\x8bsynthetic', 'archive.gz'), (b'MZsynthetic', 'program.exe'), (b'\x7fELFsynthetic', 'program.txt'), (bytes.fromhex('d0cf11e0a1b11ae1'), 'document.doc'), (b'Synthetic textual placeholder', 'document.xls'), (b'Synthetic textual placeholder', 'document.ppt'), (b'Synthetic textual placeholder', 'document.unknown'), (b'binary\x00data', 'document.txt'), (b'invalid\xff', 'document.txt'), (b'\xff\xfe\x00', 'document.txt'), ('합성 문서'.encode('utf-16-le'), 'document.txt')])
def test_unsupported_or_insufficient_inspection_is_fail_closed(data, filename):
    assert_blocked(data, filename)

def test_input_byte_limit_is_independent_of_text_privacy_result():
    assert_blocked(b'x' * (8 * 1024 * 1024 + 1), 'document.txt')

@pytest.mark.parametrize('suffix', list(MAIN_PARTS))
def test_text_only_office_extracts_actual_body(suffix):
    clean = inspect_document(office_document(suffix), 'document' + suffix)
    assert clean.counts == {}
    report = inspect_document(office_document(suffix, EMAIL), 'document' + suffix)
    assert report.counts['email'] == 1
    assert report.requires_confirmation
    assert EMAIL not in repr(report)

@pytest.mark.parametrize(('part', 'xml'), [('word/header1.xml', f'<header><t>{EMAIL}</t></header>'), ('word/footnotes.xml', f'<footnotes><t>{EMAIL}</t></footnotes>'), ('word/comments.xml', f'<comments><t>{EMAIL}</t></comments>'), ('docProps/core.xml', f'<properties><creator>{EMAIL}</creator></properties>'), ('customXml/item1.xml', f'<root value="{EMAIL}"/>'), ('customXml/item2.xml', f'<root><!-- {EMAIL} --></root>'), ('customXml/item3.xml', f'<root><?fixture {EMAIL}?></root>')])
def test_every_xml_part_metadata_attribute_comment_and_pi_is_inspected(part, xml):
    report = inspect_document(office_document(parts={part: xml.encode()}), 'document.docx')
    assert report.counts['email'] == 1

def test_office_split_runs_cannot_hide_personal_information():
    body = '<p><r><t>fixture.person@</t></r><r><t>example.invalid</t></r></p>'
    report = inspect_document(office_document(body_xml=body), 'document.docx')
    assert report.counts['email'] == 1

@pytest.mark.parametrize('where', ['filename', 'archive_comment', 'member_comment'])
def test_zip_nonbody_metadata_is_not_silently_ignored(where):
    kwargs = {}
    if where == 'filename':
        kwargs['parts'] = {f'customXml/{EMAIL}.xml': b'<root/>'}
    else:
        kwargs[where] = EMAIL.encode()
    report = inspect_document(office_document(**kwargs), 'document.docx')
    assert report.counts['email'] == 1

@pytest.mark.parametrize('part', ['word/media/image1.png', 'docProps/thumbnail.jpeg', 'word/embeddings/oleObject1.bin', 'word/vbaProject.bin', 'word/printerSettings/printerSettings1.bin', 'custom/payload.bin'])
def test_office_uninspected_media_or_binary_part_is_fail_closed(part):
    assert_blocked(office_document(parts={part: b'synthetic uninspected bytes'}), 'document.docx')

def test_external_office_relationship_is_fail_closed_without_fetching():
    xml = '<Relationships><Relationship Id="external1" TargetMode="External" Target="https://example.invalid/private-content"/></Relationships>'
    assert_blocked(office_document(parts={'word/_rels/document.xml.rels': xml.encode()}), 'document.docx', 'https://example.invalid/private-content')

@pytest.mark.parametrize('xml', [b'<!DOCTYPE root [<!ENTITY fixture "synthetic">]><root>&fixture;</root>', b'<!DOCTYPE root SYSTEM "file:///synthetic-private-path"><root/>', b'<root><broken></root>', b'<root>invalid\xff</root>', ('<root>' * 100 + 'text' + '</root>' * 100).encode()])
def test_office_xml_entities_errors_and_depth_limits_are_fail_closed(xml):
    assert_blocked(office_document(parts={'customXml/item.xml': xml}), 'document.docx', 'file:///synthetic-private-path')

def test_office_credentials_in_metadata_are_not_confirmable_personal_information():
    content = b'<root><password>synthetic-authentication-value</password></root>'
    assert_blocked(office_document(parts={'customXml/item.xml': content}), 'document.docx', 'synthetic-authentication-value')

def test_office_credential_key_and_value_split_across_elements_stays_blocked():
    body = '<p><r><t>password:</t></r><r><t> synthetic-authentication-value</t></r></p>'
    assert_blocked(office_document(body_xml=body), 'document.docx', 'synthetic-authentication-value')

@pytest.mark.parametrize('path', ['../secret.xml', '/absolute.xml', 'customXml/../secret.xml', 'customXml\\part.xml'])
def test_office_unsafe_archive_paths_are_fail_closed(path):
    assert_blocked(office_document(parts={path: b'<root/>'}), 'document.docx')

def test_duplicate_office_member_is_fail_closed():
    data = io.BytesIO(office_document())
    with pytest.warns(UserWarning, match='Duplicate'):
        with zipfile.ZipFile(data, 'a') as archive:
            archive.writestr('word/document.xml', b'<document><t>second</t></document>')
    assert_blocked(data.getvalue(), 'document.docx')

def test_encrypted_office_member_flag_is_fail_closed_without_password_attempt():
    data = bytearray(office_document())
    offset = 0
    while True:
        offset = data.find(b'PK\x01\x02', offset)
        if offset < 0:
            break
        flags = struct.unpack_from('<H', data, offset + 8)[0]
        struct.pack_into('<H', data, offset + 8, flags | 1)
        offset += 4
    assert_blocked(bytes(data), 'document.docx')

def test_compression_bomb_is_refused_before_expanding_unbounded_text():
    assert_blocked(office_document(parts={'customXml/bomb.xml': b'<root>' + b'x' * 20000000 + b'</root>'}), 'document.docx')

def test_excessive_office_part_count_is_fail_closed():
    parts = {f'customXml/item-{index}.xml': b'<root/>' for index in range(513)}
    assert_blocked(office_document(parts=parts), 'document.docx')

def test_corrupted_office_archive_is_fail_closed_without_raw_parser_details():
    assert_blocked(b'PK\x03\x04synthetic confidential detail', 'document.docx', 'synthetic confidential detail')

def test_arbitrary_zip_cannot_be_relabelled_as_office():
    data = io.BytesIO()
    with zipfile.ZipFile(data, 'w') as archive:
        archive.writestr('arbitrary.xml', b'<root>synthetic</root>')
    assert_blocked(data.getvalue(), 'document.docx')

def test_office_format_main_part_must_match_extension():
    assert_blocked(office_document('.docx'), 'document.xlsx')

@pytest.mark.parametrize(('data', 'filename'), [(b'<root>fixture.person&#64;example.invalid</root>', 'document.xml'), (b'<html><p>fixture.person&#64;example.invalid</p></html>', 'document.html'), (b'<root value="fixture.person&#64;example.invalid"/>', 'document.xml'), (b'{"contact": "fixture.person\\u0040example.invalid"}', 'document.json'), (b'{"contact": "fixture.person\\u0040example.invalid"}\n', 'document.jsonl'), (b'<html><!-- fixture.person&#64;example.invalid --></html>', 'document.html')])
def test_restored_document_text_views_are_inspected(data, filename):
    report = inspect_document(data, filename)
    assert report.counts['email'] == 1

@pytest.mark.parametrize(('data', 'filename'), [(b'<root><password>synthetic-authentication-value</password></root>', 'document.xml'), (b'<root>password: synthetic&#45;authentication&#45;value</root>', 'document.xml'), (b'<html><p>password&#58; synthetic-authentication-value</p></html>', 'document.html'), (b'{"pass\\u0077ord": "synthetic-authentication-value"}', 'document.json')])
def test_restored_authentication_values_cannot_be_confirmed(data, filename):
    assert_blocked(data, filename, 'synthetic-authentication-value')

@pytest.mark.parametrize(('data', 'filename'), [(b'<root><broken></root>', 'document.xml'), (b'{"contact": ', 'document.json'), (b'{"contact": "public"}\nnot-json\n', 'document.jsonl'), (b'<!DOCTYPE root [<!ENTITY fixture "public">]><root>&fixture;</root>', 'document.xml')])
def test_structured_document_extraction_failure_does_not_fall_back_to_raw_text(data, filename):
    assert_blocked(data, filename)

@pytest.mark.parametrize('element', ['<img src="data:image/png;base64,synthetic">', '<svg><path d="M0 0L1 1"/></svg>', '<object data="embedded.bin"></object>', '<script>syntheticContent()</script>', '<link rel="stylesheet" href="https://example.invalid/style.css">'])
def test_html_uninspected_rendered_or_external_content_is_held(element):
    assert_blocked(element.encode(), 'document.html')

@pytest.mark.parametrize('part', ['word/media/image.xml', 'docProps/thumbnail.xml', 'word/embeddings/oleObject.xml', 'word/vbaProject.xml', 'word/activeX/activeX1.xml'])
def test_renamed_office_media_paths_remain_uninspected(part):
    assert_blocked(office_document(parts={part: b'<root>synthetic</root>'}), 'document.docx')

@pytest.mark.parametrize('content_type', ['image/svg+xml', 'font/woff', 'application/octet-stream', 'application/vnd.ms-office.vbaProject', 'application/vnd.ms-office.oleObject'])
def test_office_image_or_unknown_content_type_cannot_hide_in_xml_suffix(content_type):
    types = f'<Types><Override PartName="/word/document.xml" ContentType="application/xml"/><Override PartName="/customXml/item.xml" ContentType="{content_type}"/></Types>'
    assert_blocked(office_document(parts={'[Content_Types].xml': types.encode(), 'customXml/item.xml': b'<root/>'}), 'document.docx')

@pytest.mark.parametrize('tag', ['svg', 'blip', 'imagedata', 'oleObject', 'altChunk', 'pict', 'shape'])
def test_office_uninspected_visual_elements_are_held_even_without_binary_parts(tag):
    assert_blocked(office_document(body_xml=f'<document><{tag}/></document>'), 'document.docx')

def test_nested_json_labels_are_inspected_after_decoding():
    data = b'{"person": {"name": "Synthetic Person", "address": "0 Synthetic Example Road"}}'
    report = inspect_document(data, 'document.json')
    assert report.counts['person_name'] >= 1
    assert report.counts['address'] >= 1

def test_bounded_document_view_quantity_fails_closed(monkeypatch):
    import nyanya_agent.upload_document_privacy as privacy
    monkeypatch.setattr(privacy, 'MAX_INSPECTION_CHARS', 32, raising=False)
    assert_blocked(b'x' * 33, 'document.txt')

def test_bounded_personal_information_match_quantity_fails_closed(monkeypatch):
    import nyanya_agent.upload_document_privacy as privacy
    monkeypatch.setattr(privacy, 'MAX_FINDINGS_PER_KIND', 1, raising=False)
    assert_blocked((EMAIL + ' second.fixture@example.invalid').encode(), 'document.txt')

def test_elapsed_document_inspection_cannot_return_clean_report(monkeypatch):
    import nyanya_agent.upload_document_privacy as privacy
    monkeypatch.setattr(privacy, 'MAX_INSPECTION_SECONDS', -1, raising=False)
    assert_blocked(b'Synthetic public description.', 'document.txt')

def office_with_gap(*, inside_compressed_member=False):
    data = bytearray(office_document())
    marker = b'uninspected.fixture@example.invalid'
    end = data.rfind(b'PK\x05\x06')
    central = struct.unpack_from('<I', data, end + 16)[0]
    if inside_compressed_member:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = max(archive.infolist(), key=lambda item: item.header_offset)
        struct.pack_into('<I', data, info.header_offset + 18, info.compress_size + len(marker))
    data[central:central] = marker
    new_end = end + len(marker)
    struct.pack_into('<I', data, new_end + 16, central + len(marker))
    if inside_compressed_member:
        cursor = central + len(marker)
        while cursor < new_end:
            name_size, extra_size, comment_size = struct.unpack_from('<HHH', data, cursor + 28)
            offset = struct.unpack_from('<I', data, cursor + 42)[0]
            if offset == info.header_offset:
                struct.pack_into('<I', data, cursor + 20, info.compress_size + len(marker))
            cursor += 46 + name_size + extra_size + comment_size
    return bytes(data)

def test_unlisted_zip_gap_before_central_directory_is_not_inspected_coverage():
    assert_blocked(office_with_gap(), 'document.docx', 'uninspected.fixture@example.invalid')

def test_unused_bytes_after_deflate_eof_are_not_inspected_coverage():
    assert_blocked(office_with_gap(inside_compressed_member=True), 'document.docx', 'uninspected.fixture@example.invalid')

def test_unsupported_zip_data_descriptor_mode_is_held():
    data = bytearray(office_document())
    for signature, flag_offset in ((b'PK\x03\x04', 6), (b'PK\x01\x02', 8)):
        cursor = 0
        while True:
            cursor = data.find(signature, cursor)
            if cursor < 0:
                break
            flags = struct.unpack_from('<H', data, cursor + flag_offset)[0]
            struct.pack_into('<H', data, cursor + flag_offset, flags | 8)
            cursor += 4
    assert_blocked(bytes(data), 'document.docx')

@pytest.mark.parametrize(('data', 'filename'), [(b'![scan](https://example.invalid/scan.png)', 'document.md'), (b'![scan][source]\n[source]: https://example.invalid/scan.png', 'document.md'), (b'![scan]\n[scan]: scan.png', 'document.md'), (b'.. image:: scan.png', 'document.rst'), (b'.. figure:: scan.png', 'document.rst'), (b'.. |scan| image:: scan.png', 'document.rst'), (b'<canvas>synthetic</canvas>', 'document.md'), (b'<style>.scan { background: url(scan.png); }</style>', 'document.html'), (b"<root><svg><path d='M0 0L1 1'/></svg></root>", 'document.xml')])
def test_document_visual_references_cannot_be_reported_as_inspected(data, filename):
    assert_blocked(data, filename)

def test_source_code_is_scanned_as_text_without_execution_or_rendering():
    report = inspect_document(b'print("<img src=synthetic.png>")\n', 'source.py')
    assert not report.requires_confirmation

@pytest.mark.parametrize('corruption', ['crc', 'central_signature', 'local_filename'])
def test_zip_parser_errors_never_expose_raw_document_details(corruption):
    data = bytearray(office_document())
    end = data.rfind(b'PK\x05\x06')
    central = struct.unpack_from('<I', data, end + 16)[0]
    if corruption == 'crc':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = max(archive.infolist(), key=lambda item: item.header_offset)
        fake_crc = info.CRC ^ 1
        struct.pack_into('<I', data, info.header_offset + 14, fake_crc)
        cursor = central
        while cursor < end:
            name_size, extra_size, comment_size = struct.unpack_from('<HHH', data, cursor + 28)
            if struct.unpack_from('<I', data, cursor + 42)[0] == info.header_offset:
                struct.pack_into('<I', data, cursor + 16, fake_crc)
            cursor += 46 + name_size + extra_size + comment_size
    elif corruption == 'central_signature':
        data[central:central + 4] = b'BAD!'
    else:
        data[30] ^= 1
    assert_blocked(bytes(data), 'document.docx', 'Bad CRC', 'Bad magic', 'File name', '[Content_Types]')

def test_office_metadata_extra_field_is_not_treated_as_inspected_text():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        info = zipfile.ZipInfo('synthetic.xml')
        info.extra = struct.pack('<HH', 65535, 7) + b'private'
        archive.writestr(info, b'<root/>')
    assert_blocked(output.getvalue(), 'document.docx', 'private')

def test_duplicate_html_attributes_cannot_hide_a_credential_field():
    assert_blocked(b"<input name='password' name='safe' value='synthetic-private-value'>", 'document.html', 'synthetic-private-value')

def test_duplicate_local_xml_attributes_cannot_hide_a_credential_field():
    assert_blocked(b"<entry xmlns:a='urn:a' xmlns:b='urn:b' a:name='password' b:name='safe' value='synthetic-private-value'/>", 'document.xml', 'synthetic-private-value')

def test_duplicate_decoded_json_keys_cannot_hide_credentials():
    assert_blocked(b'{"\\u0070assword":"synthetic-private-value","password":""}', 'document.json', 'synthetic-private-value')

def test_directory_entry_cannot_hide_uninspected_compressed_payload():
    data = bytearray(office_document(parts={'extra/': b'uninspected synthetic payload'}))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        info = archive.getinfo('extra/')
    struct.pack_into('<I', data, info.header_offset + 14, 0)
    struct.pack_into('<I', data, info.header_offset + 22, 0)
    cursor = 0
    while True:
        cursor = data.find(b'PK\x01\x02', cursor)
        assert cursor >= 0
        size = struct.unpack_from('<H', data, cursor + 28)[0]
        if data[cursor + 46:cursor + 46 + size] == b'extra/':
            struct.pack_into('<I', data, cursor + 16, 0)
            struct.pack_into('<I', data, cursor + 24, 0)
            break
        cursor += 4
    assert_blocked(bytes(data), 'document.docx')
