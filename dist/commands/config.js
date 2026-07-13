"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.printConfigStatus = printConfigStatus;
exports.configure = configure;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const env_file_1 = require("../runtime/env-file");
const project_1 = require("../runtime/project");
const prompt_1 = require("../runtime/prompt");
function ensureEnvFile(layout) {
    (0, project_1.ensureRuntimeDirectories)(layout);
    if (fs_1.default.existsSync(layout.envPath)) {
        (0, project_1.chmodOwnerOnly)(layout.envPath);
        return;
    }
    const samplePath = path_1.default.join(layout.codeRoot, ".env.example");
    if (!fs_1.default.existsSync(samplePath)) {
        throw new Error(`Missing environment template: ${samplePath}`);
    }
    fs_1.default.copyFileSync(samplePath, layout.envPath);
    (0, project_1.chmodOwnerOnly)(layout.envPath);
}
function printValidation(layout) {
    const validation = (0, env_file_1.readEnvFile)(layout.envPath);
    console.log(`env_file=${layout.envPath}`);
    for (const warning of validation.warnings) {
        console.log(`config_warning=${warning}`);
    }
    for (const error of validation.errors) {
        console.error(`config_error=${error}`);
    }
    console.log(`config_valid=${validation.errors.length === 0}`);
    return validation.errors.length === 0 ? 0 : 1;
}
function printConfigStatus(projectRoot) {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    const validation = (0, env_file_1.readEnvFile)(layout.envPath);
    const values = validation.values;
    const host = values.NYANYA_DASHBOARD_HOST || "127.0.0.1";
    const port = values.NYANYA_DASHBOARD_PORT || "8765";
    console.log(`code_root=${layout.codeRoot}`);
    console.log(`state_root=${layout.stateRoot}`);
    console.log(`state_mode=${layout.legacyState ? "legacy-source" : "user"}`);
    console.log(`env_file=${layout.envPath}`);
    console.log(`provider=${values.NYANYA_PROVIDER || "gemini_cli"}`);
    console.log(`model=${values.NYANYA_MODEL || values.NYANYA_GEMINI_MODEL || "default"}`);
    console.log(`discord_configured=${(0, env_file_1.secretConfigured)(values, "NYANYA_DISCORD_BOT_TOKEN") || Boolean(process.env.DISCORD_BOT_TOKEN)}`);
    console.log(`telegram_configured=${(0, env_file_1.secretConfigured)(values, "NYANYA_TELEGRAM_BOT_TOKEN")}`);
    console.log(`openai_api_key_configured=${(0, env_file_1.secretConfigured)(values, "NYANYA_OPENAI_API_KEY")}`);
    console.log(`dashboard_url=http://${host}:${port}`);
    for (const warning of validation.warnings) {
        console.log(`config_warning=${warning}`);
    }
    for (const error of validation.errors) {
        console.error(`config_error=${error}`);
    }
    return validation.errors.length === 0 ? 0 : 1;
}
function configureProvider(values, updates) {
    const current = values.NYANYA_PROVIDER || "gemini_cli";
    const choices = [
        "Antigravity/Gemini CLI (Google OAuth)",
        "Ollama local model",
        "OpenAI-compatible API",
        "Keep current provider"
    ];
    const currentIndex = current === "ollama" ? 1 : current === "openai_compatible" ? 2 : 0;
    const selected = (0, prompt_1.choose)("LLM provider", choices, currentIndex);
    if (selected === 3) {
        return;
    }
    if (selected === 0) {
        updates.NYANYA_PROVIDER = "gemini_cli";
        updates.NYANYA_GEMINI_CLI = (0, prompt_1.ask)("Gemini-compatible CLI", values.NYANYA_GEMINI_CLI || "gemini");
        updates.NYANYA_MODEL = (0, prompt_1.ask)("Model override (blank uses CLI default)", values.NYANYA_MODEL || "");
        console.log("auth_next=Complete Google OAuth in the selected CLI, then run nyanya doctor --backend");
        return;
    }
    if (selected === 1) {
        updates.NYANYA_PROVIDER = "ollama";
        updates.NYANYA_OLLAMA_BASE_URL = (0, prompt_1.ask)("Ollama base URL", values.NYANYA_OLLAMA_BASE_URL || "http://127.0.0.1:11434");
        updates.NYANYA_OLLAMA_MODEL = (0, prompt_1.ask)("Ollama model", values.NYANYA_OLLAMA_MODEL || "qwen3:4b");
        return;
    }
    updates.NYANYA_PROVIDER = "openai_compatible";
    updates.NYANYA_OPENAI_BASE_URL = (0, prompt_1.ask)("OpenAI-compatible base URL", values.NYANYA_OPENAI_BASE_URL || "http://127.0.0.1:8000");
    updates.NYANYA_MODEL = (0, prompt_1.ask)("Model", values.NYANYA_MODEL || "");
    const apiKey = (0, prompt_1.ask)("API key (blank keeps current value)", "", true);
    if (apiKey) {
        updates.NYANYA_OPENAI_API_KEY = apiKey;
    }
}
function configureConnectors(values, updates) {
    const discordConfigured = Boolean(values.NYANYA_DISCORD_BOT_TOKEN || process.env.NYANYA_DISCORD_BOT_TOKEN || process.env.DISCORD_BOT_TOKEN);
    if ((0, prompt_1.confirm)("Configure Discord connector", discordConfigured)) {
        const token = (0, prompt_1.ask)("Discord bot token (blank keeps current value)", "", true);
        if (token) {
            updates.NYANYA_DISCORD_BOT_TOKEN = token;
        }
        updates.NYANYA_DISCORD_PREFIX = (0, prompt_1.ask)("Discord command prefix", values.NYANYA_DISCORD_PREFIX || "!nyanya");
        updates.NYANYA_DISCORD_ALLOWED_CHANNEL_IDS = (0, prompt_1.ask)("Allowed channel IDs (comma separated)", values.NYANYA_DISCORD_ALLOWED_CHANNEL_IDS || "");
        updates.NYANYA_DISCORD_ALLOWED_USER_IDS = (0, prompt_1.ask)("Allowed user IDs (comma separated, optional)", values.NYANYA_DISCORD_ALLOWED_USER_IDS || "");
        updates.NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS = (0, prompt_1.ask)("File-share channel IDs (comma separated)", values.NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS || "");
    }
    const telegramConfigured = Boolean(values.NYANYA_TELEGRAM_BOT_TOKEN || process.env.NYANYA_TELEGRAM_BOT_TOKEN);
    if ((0, prompt_1.confirm)("Configure Telegram connector", telegramConfigured)) {
        const token = (0, prompt_1.ask)("Telegram bot token (blank keeps current value)", "", true);
        if (token) {
            updates.NYANYA_TELEGRAM_BOT_TOKEN = token;
        }
        updates.NYANYA_TELEGRAM_ALLOWED_CHAT_IDS = (0, prompt_1.ask)("Allowed chat IDs (comma separated)", values.NYANYA_TELEGRAM_ALLOWED_CHAT_IDS || "");
        updates.NYANYA_TELEGRAM_ALLOWED_USER_IDS = (0, prompt_1.ask)("Allowed user IDs (comma separated, optional)", values.NYANYA_TELEGRAM_ALLOWED_USER_IDS || "");
    }
}
function configure(projectRoot, args = [], mode = "all") {
    const layout = (0, project_1.resolveRuntimeLayout)(projectRoot);
    try {
        ensureEnvFile(layout);
    }
    catch (error) {
        console.error(`config_error=${error instanceof Error ? error.message : String(error)}`);
        return 1;
    }
    const command = args[0] || "edit";
    if (command === "show") {
        return printConfigStatus(projectRoot);
    }
    if (command === "validate") {
        return printValidation(layout);
    }
    if (!(0, prompt_1.interactiveAvailable)()) {
        console.error("Interactive terminal required. Use `nyanya config show` or edit the reported env_file directly.");
        console.error(`env_file=${layout.envPath}`);
        return 2;
    }
    const current = (0, env_file_1.readEnvFile)(layout.envPath);
    if (current.errors.length > 0) {
        for (const error of current.errors) {
            console.error(`config_error=${error}`);
        }
        return 1;
    }
    const updates = {};
    configureProvider(current.values, updates);
    if (mode === "all") {
        configureConnectors(current.values, updates);
    }
    (0, env_file_1.updateEnvFile)(layout.envPath, updates);
    console.log(`config_saved=${layout.envPath}`);
    return printValidation(layout);
}
