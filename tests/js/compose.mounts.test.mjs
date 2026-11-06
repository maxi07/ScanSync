import test from "node:test";
import assert from "node:assert/strict";
import { statSync } from "node:fs";

test("development PDF preview volume mount point is included in the checkout", () => {
    const placeholder = new URL("../../web_service/src/static/images/pdfpreview/.gitkeep", import.meta.url);

    assert.equal(statSync(placeholder).isFile(), true);
});