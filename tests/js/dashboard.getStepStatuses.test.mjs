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
    for (const ocrStatus of ["NO_TEXT", "UNSUPPORTED", "DPI_ERROR", "INPUT_ERROR", "OUTPUT_ERROR"]) {
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

// Mirror how addPdfCard / updateProgressBar derive the branch flags from the data.
function deriveFlags(fileStatus, progressStep) {
    const s = (fileStatus || "").toLowerCase();
    const isDeleted = s.includes("deleted");
    const isFailed = s.includes("failed") || isDeleted || progressStep === -1;
    const isCompleted = s.includes("completed");
    return { isFailed, isDeleted, isCompleted };
}

function statusesFor(fileStatus, progressStep, extra = {}) {
    const { isFailed, isDeleted, isCompleted } = deriveFlags(fileStatus, progressStep);
    return getStepStatuses(progressStep, isFailed, isDeleted, isCompleted, {
        file_status: fileStatus,
        ...extra
    });
}

// Every in-progress pipeline state must place exactly one "current" (marquee)
// segment on the stage the pipeline has actually reached. status_progressbar
// values mirror StatusProgressBar._progress_map on the server.
const inProgressCases = [
    { file_status: "File Not Ready", pb: 0, current: 0 },
    { file_status: "Reading Metadata", pb: 1, current: 1 },
    { file_status: "OCR Pending", pb: 1, current: 2 },
    { file_status: "OCR Processing", pb: 2, current: 2 },
    { file_status: "File Name Pending", pb: 2, current: 3 },
    { file_status: "File Name Processing", pb: 3, current: 3 },
    { file_status: "Sync Pending", pb: 3, current: 4 },
    { file_status: "Syncing", pb: 4, current: 4 }
];

for (const { file_status, pb, current } of inProgressCases) {
    test(`in-progress "${file_status}" marks exactly one current step at index ${current}`, () => {
        const statuses = statusesFor(file_status, pb);
        const currentIndexes = Array.from(statuses).map((s, i) => (s === "current" ? i : -1)).filter((i) => i >= 0);
        assert.deepEqual(currentIndexes, [current], `single marquee step expected at ${current}`);
        // Everything before the current step is done, everything after is pending.
        for (let i = 0; i < 5; i++) {
            if (i < current) assert.equal(statuses[i], "completed", `step ${i} should be completed`);
            if (i > current) assert.equal(statuses[i], "pending", `step ${i} should be pending`);
        }
    });
}

// Terminal states never show a marquee (no "current" segment).
const terminalCases = [
    { file_status: "Completed", pb: 5, expected: ["completed", "completed", "completed", "completed", "completed"] },
    { file_status: "Invalid File", pb: -1, expected: ["failed", "pending", "pending", "pending", "pending"] },
    { file_status: "Sync Failed", pb: -1, expected: ["completed", "completed", "completed", "completed", "failed"] },
    { file_status: "Deleted", pb: -1, expected: ["failed", "failed", "failed", "failed", "failed"] }
];

for (const { file_status, pb, expected } of terminalCases) {
    test(`terminal "${file_status}" shows no marquee and renders as expected`, () => {
        const statuses = statusesFor(file_status, pb, { ocr_status: "COMPLETED", file_naming_status: "COMPLETED" });
        assert.ok(!statuses.includes("current"), "terminal state must not show a current/marquee step");
        assert.deepEqual(Array.from(statuses), expected);
    });
}

