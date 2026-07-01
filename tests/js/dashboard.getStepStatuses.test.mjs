import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

// Load the real dashboard.js into an isolated context without modifying it.
// dashboard.js is a browser global script, so we stub the only top-level
// side effect (document.addEventListener) and read the pure functions back
// out of the sandbox global object.
const here = dirname(fileURLToPath(import.meta.url));
const dashboardSource = readFileSync(
    join(here, "..", "..", "web_service", "src", "static", "js", "dashboard.js"),
    "utf8"
);

const sandbox = {
    document: { addEventListener() {} },
    console: { log() {}, warn() {}, error() {} }
};
vm.createContext(sandbox);
vm.runInContext(dashboardSource, sandbox);

const { getStepStatuses } = sandbox;

test("getStepStatuses exists after loading dashboard.js", () => {
    assert.equal(typeof getStepStatuses, "function");
});

test("failed OCR is failed while file naming becomes the active (current) step", () => {
    // file_status "File Name Pending" maps to progressStep 2, the same index as
    // the OCR step. Processing continues after a non-fatal OCR failure, so the
    // OCR step must be marked failed and the file naming step must become the
    // active ("current") step so its marquee animation is shown.
    const statuses = getStepStatuses(2, false, false, false, {
        file_status: "File Name Pending",
        ocr_status: "FAILED",
        file_naming_status: "PENDING"
    });

    assert.deepEqual(Array.from(statuses), ["completed", "completed", "failed", "current", "pending"]);
});

test("sync pending marks upload as the active step (not file naming)", () => {
    // "Sync Pending" maps to progressStep 3, but the upload step (index 4) is the
    // one actually waiting to run.
    const statuses = getStepStatuses(3, false, false, false, {
        file_status: "Sync Pending",
        ocr_status: "COMPLETED",
        file_naming_status: "COMPLETED"
    });

    assert.deepEqual(Array.from(statuses), ["completed", "completed", "completed", "completed", "current"]);
});

test("failed OCR is shown as failed even when the document completed overall", () => {
    const statuses = getStepStatuses(5, false, false, true, {
        file_status: "Completed",
        ocr_status: "FAILED"
    });

    assert.equal(statuses[2], "failed");
});

test("completed doc with failed OCR and failed file naming (real reload data)", () => {
    // Mirrors the real DB state after a non-fatal OCR failure: the document is
    // uploaded (Completed) but ocr_jobs and file_naming_jobs both recorded a
    // failure. Both stages must render red on page reload.
    const statuses = getStepStatuses(5, false, false, true, {
        file_status: "Completed",
        status_progressbar: 5,
        ocr_status: "FAILED",
        file_naming_status: "RATE_LIMIT_ERROR"
    });

    assert.deepEqual(Array.from(statuses), ["completed", "completed", "failed", "failed", "completed"]);
});

test("non-failure OCR status keeps the OCR step as current when it is the active step", () => {
    const statuses = getStepStatuses(2, false, false, false, {
        file_status: "OCR Processing",
        ocr_status: "PROCESSING"
    });

    assert.deepEqual(Array.from(statuses), ["completed", "completed", "current", "pending", "pending"]);
});

test("successful OCR shows the OCR step as completed once processing moved on", () => {
    const statuses = getStepStatuses(3, false, false, false, {
        file_status: "File Name Processing",
        ocr_status: "COMPLETED",
        file_naming_status: "PROCESSING"
    });

    assert.equal(statuses[2], "completed");
    assert.equal(statuses[3], "current");
});

test("other OCR failure variants are surfaced as failed", () => {
    for (const ocrStatus of ["UNSUPPORTED", "DPI_ERROR", "INPUT_ERROR", "OUTPUT_ERROR"]) {
        const statuses = getStepStatuses(2, false, false, false, {
            file_status: "File Name Pending",
            ocr_status: ocrStatus
        });
        assert.equal(statuses[2], "failed", `expected failed for ${ocrStatus}`);
    }
});

test("file naming failure is surfaced as failed at its step", () => {
    const statuses = getStepStatuses(3, false, false, false, {
        file_status: "Sync Pending",
        ocr_status: "COMPLETED",
        file_naming_status: "NO_OCR_FILE"
    });

    assert.equal(statuses[3], "failed");
});
