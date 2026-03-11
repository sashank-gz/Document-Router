/**
 * Document Router Platform — Frontend Logic
 *
 * Handles: drag-drop upload, API calls, result cards, jobs table, toasts
 */

const API_BASE = "";  // same origin

// ── DOM refs ──────────────────────────────────────────────────
const uploadZone = document.getElementById("upload-zone");
const fileInput = document.getElementById("file-input");
const browseBtn = document.getElementById("browse-btn");
const uploadProgress = document.getElementById("upload-progress");
const progressTitle = document.getElementById("progress-title");
const progressCount = document.getElementById("progress-count");
const progressBar = document.getElementById("progress-bar");
const resultsSection = document.getElementById("results-section");
const resultsGrid = document.getElementById("results-grid");
const clearResultsBtn = document.getElementById("clear-results-btn");
const jobsTbody = document.getElementById("jobs-tbody");
const refreshJobsBtn = document.getElementById("refresh-jobs-btn");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const toastContainer = document.getElementById("toast-container");

// ── Health check on load ──────────────────────────────────────
async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/health`);
        const data = await res.json();
        statusDot.className = "status-dot online";
        statusText.textContent = `Online • ${data.version || "v2.0"}`;
    } catch {
        statusDot.className = "status-dot offline";
        statusText.textContent = "Offline";
    }
}

// ── Toast notifications ───────────────────────────────────────
function showToast(message, type = "info") {
    const icons = { success: "✓", error: "✕", info: "i" };
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || "i"}</span>
        <span>${message}</span>
    `;
    toastContainer.appendChild(toast);
    setTimeout(() => {
        toast.classList.add("removing");
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Drag and drop ─────────────────────────────────────────────
uploadZone.addEventListener("click", () => fileInput.click());
browseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
});

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
        handleFiles(fileInput.files);
        fileInput.value = "";
    }
});

["dragenter", "dragover"].forEach(evt => {
    uploadZone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.add("drag-over");
    });
});

["dragleave", "drop"].forEach(evt => {
    uploadZone.addEventListener(evt, (e) => {
        e.preventDefault();
        e.stopPropagation();
        uploadZone.classList.remove("drag-over");
    });
});

uploadZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFiles(files);
});

// ── File upload ───────────────────────────────────────────────
async function handleFiles(fileList) {
    const files = Array.from(fileList).filter(f => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));

    if (files.length === 0) {
        showToast("Please select PDF files only", "error");
        return;
    }

    // Show progress
    uploadProgress.hidden = false;
    progressTitle.textContent = "Processing documents...";
    progressCount.textContent = `0 / ${files.length}`;
    progressBar.style.width = "0%";

    const formData = new FormData();
    files.forEach(file => formData.append("files", file));

    try {
        // Animate progress smoothly
        progressBar.style.width = "30%";

        const res = await fetch(`${API_BASE}/upload`, {
            method: "POST",
            body: formData,
        });

        progressBar.style.width = "80%";

        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.detail || `Upload failed (${res.status})`);
        }

        const data = await res.json();
        progressBar.style.width = "100%";
        progressCount.textContent = `${data.count} / ${files.length}`;
        progressTitle.textContent = "Complete!";

        showToast(`${data.count} document(s) classified successfully`, "success");
        displayResults(data.results);
        loadJobs();

        // Hide progress after a moment
        setTimeout(() => {
            uploadProgress.hidden = true;
            progressBar.style.width = "0%";
        }, 2000);

    } catch (err) {
        progressBar.style.width = "0%";
        uploadProgress.hidden = true;
        showToast(err.message || "Upload failed", "error");
    }
}

// ── Display Results ───────────────────────────────────────────
function displayResults(results) {
    resultsSection.hidden = false;

    results.forEach((r, i) => {
        const card = document.createElement("div");
        card.className = "result-card";
        card.style.animationDelay = `${i * 0.08}s`;

        const pipelineClass = (r.pipeline || "MANUAL").toLowerCase();
        const confidence = r.confidence ?? 1;
        const confidencePercent = Math.round(confidence * 100);
        const confLevel = confidence >= 0.8 ? "high" : confidence >= 0.5 ? "medium" : "low";

        let debugHtml = "";
        if (r.debug) {
            const debugId = `debug-${Date.now()}-${i}`;
            debugHtml = `
                <button class="debug-toggle" onclick="toggleDebug('${debugId}')">
                    ▸ Debug info
                </button>
                <div class="debug-content" id="${debugId}" hidden>${JSON.stringify(r.debug, null, 2)}</div>
            `;
        }

        card.innerHTML = `
            <div class="result-info">
                <div class="result-filename">${escapeHtml(r.file_name || "Unknown")}</div>
                <div class="result-meta">
                    <span class="badge badge-type">${r.document_type || "UNKNOWN"}</span>
                    <span class="badge badge-${pipelineClass}">${r.pipeline || "MANUAL"}</span>
                    <span class="badge badge-tier">Tier: ${r.classification_tier || "—"}</span>
                    <div class="confidence-meter">
                        <div class="confidence-bar">
                            <div class="confidence-fill ${confLevel}" style="width: ${confidencePercent}%"></div>
                        </div>
                        <span class="confidence-value">${confidencePercent}%</span>
                    </div>
                </div>
                ${debugHtml}
                ${r.message ? `<div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 4px;">${escapeHtml(r.message)}</div>` : ""}
            </div>
            <div class="result-badges">
                <span class="badge badge-status ${(r.status || "").toLowerCase()}">${r.status || "—"}</span>
                <span style="font-size: 0.7rem; color: var(--text-muted);">Job #${r.job_id || "—"}</span>
            </div>
        `;

        resultsGrid.prepend(card);
    });
}

function toggleDebug(id) {
    const el = document.getElementById(id);
    if (el) {
        el.hidden = !el.hidden;
        const btn = el.previousElementSibling;
        if (btn) btn.textContent = el.hidden ? "▸ Debug info" : "▾ Debug info";
    }
}

// ── Clear results ─────────────────────────────────────────────
clearResultsBtn.addEventListener("click", () => {
    resultsGrid.innerHTML = "";
    resultsSection.hidden = true;
});

// ── Jobs table ────────────────────────────────────────────────
async function loadJobs() {
    try {
        const res = await fetch(`${API_BASE}/jobs`);
        if (!res.ok) throw new Error("Failed to load jobs");
        const jobs = await res.json();
        renderJobs(jobs);
    } catch {
        // silent fail — table stays as-is
    }
}

function renderJobs(jobs) {
    if (jobs.length === 0) {
        jobsTbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="6">No jobs yet — upload documents to get started</td>
            </tr>
        `;
        return;
    }

    jobsTbody.innerHTML = jobs.map(job => {
        const pipelineClass = (job.route || "MANUAL").toLowerCase();
        const statusClass = (job.status || "").toLowerCase();
        const created = job.created_at ? new Date(job.created_at).toLocaleString() : "—";

        return `
            <tr>
                <td>${job.id}</td>
                <td class="file-cell" title="${escapeHtml(job.file_name)}">${escapeHtml(job.file_name || "—")}</td>
                <td><span class="badge badge-type">${job.route || "—"}</span></td>
                <td><span class="badge badge-${pipelineClass}">${job.route || "—"}</span></td>
                <td><span class="badge badge-status ${statusClass}">${job.status || "—"}</span></td>
                <td>${created}</td>
            </tr>
        `;
    }).join("");
}

refreshJobsBtn.addEventListener("click", () => {
    loadJobs();
    showToast("Jobs refreshed", "info");
});

// ── Utilities ─────────────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ── Init ──────────────────────────────────────────────────────
checkHealth();
loadJobs();

// Periodically check health
setInterval(checkHealth, 30000);
