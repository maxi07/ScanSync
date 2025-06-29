import js from "@eslint/js";
import globals from "globals";
import json from "@eslint/json";
import markdown from "@eslint/markdown";
import css from "@eslint/css";
import { defineConfig } from "eslint/config";

export default defineConfig([
    {
        files: ["web_service/src/static/js/**/*.{js,mjs,cjs}"],
        plugins: { js },
        extends: ["js/recommended"],
        languageOptions: { globals: globals.browser },
        rules: {
            semi: ["warn", "always"],
            indent: ["error", 4],
            "object-curly-spacing": ["error", "always"],
            "space-before-function-paren": ["error", "never"],
            "no-unused-vars": ["warn"],
            "no-var": "error"
        }
    },
    {
        files: ["**/*.{js,mjs,cjs}"],
        plugins: { js },
        extends: ["js/recommended"],
        languageOptions: { globals: globals.browser }
    },
    { files: ["**/*.js"], languageOptions: { sourceType: "script" } },
    { files: ["**/*.json"], plugins: { json }, language: "json/json", extends: ["json/recommended"] },
    { files: ["**/*.md"], plugins: { markdown }, language: "markdown/gfm", extends: ["markdown/recommended"] },
    { files: ["**/*.css"], plugins: { css }, language: "css/css", extends: ["css/recommended"],
    rules:
        {
            "css/no-important": "off",
            "css/use-baseline": "off",
        }
    },
    {
        ignores: [
            "**/.venv",
            "**/node_modules",
            "**/package-lock.json",
        ]
    }
]);