import re

path = r"D:\projects_all_time\08 Intelligence to choose bw LLM & OCR\00 codes\doc-router\document-router-platform\static\app.js"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# We need to replace the layout string from `let exportsHtml = "";` all the way to `let debugHtml = ""; ... }`

new_layout = """
        let exportsHtml = "";
        if (job.available_outputs && job.available_outputs.length > 0) {
            const stem = job.file_name.replace(/\\.[^/.]+$/, "");
            exportsHtml = ``;
            job.available_outputs.forEach(ext => {
                exportsHtml += `<a href="/processed/${stem}.${ext.toLowerCase()}" target="_blank" style="text-decoration:none; padding:2px 6px; background:var(--bg-card); border:1px solid var(--border-color); border-radius:4px; color:var(--text-color); font-size:0.7rem;">↓ ${ext}</a> `;
            });
        }

        let logsArray = job.debug_info ? job.debug_info.logs : null;
        let logsBtn = "", logsContent = "";
        if (logsArray && Array.isArray(logsArray) && logsArray.length > 0) {
            const logsId = `logs-job-${job.id}`;
            const formattedLogs = logsArray.map(l => `<div style="margin-bottom: 2px;">${escapeHtml(l)}</div>`).join('');
            logsBtn = `<button class="btn btn-ghost" onclick="toggleDebug('${logsId}')" style="font-size: 0.7rem; padding: 2px 6px; border: 1px solid var(--border-color);">⌨ Terminal</button>`;
            logsContent = `<div class="debug-content" id="${logsId}" hidden style="margin-top: 8px; background:#111827; color:#10B981; font-family:monospace; padding:10px; border-radius:6px; width: 100%; max-height: 250px; overflow-y: auto; font-size: 0.7rem; border: 1px solid #374151;">${formattedLogs}</div>`;
            delete job.debug_info.logs;
        }

        let debugBtn = "", debugContent = "";
        if (job.debug_info && Object.keys(job.debug_info).length > 0) {
            const debugId = `debug-job-${job.id}`;
            debugBtn = `<button class="btn btn-ghost" onclick="toggleDebug('${debugId}')" style="font-size: 0.7rem; padding: 2px 6px; border: 1px solid var(--border-color);">{} JSON</button>`;
            debugContent = `<div class="debug-content" id="${debugId}" hidden style="margin-top: 8px; max-width: 100%; max-height: 200px; overflow: auto; white-space: pre-wrap; font-size: 0.7rem; background: var(--table-header-bg); padding: 8px; border-radius: 4px;">${escapeHtml(JSON.stringify(job.debug_info, null, 2))}</div>`;
        }

        let finalGroupHtml = `
            <div style="margin-top: 6px; display: flex; gap: 6px; flex-wrap: wrap; align-items: center;">
                ${exportsHtml}
                ${logsBtn}
                ${debugBtn}
            </div>
            ${logsContent}
            ${debugContent}
        `;
"""

# Regex to match the old block:
pattern = r"let exportsHtml = \"\";.*?let debugHtml = \"\";.*?\}\n"

# Replace the block
result = re.sub(pattern, new_layout.strip() + "\n", content, flags=re.DOTALL)

# Now we need to update the `return` statement in renderJobsPage to use `${finalGroupHtml}`
# instead of `${exportsHtml} ... ${logsHtml} ... ${debugHtml}`
return_pattern = r"\$\{exportsHtml\}\s*\n\s*\$\{logsHtml\}\s*\n\s*\$\{debugHtml\}"
result = re.sub(return_pattern, "${finalGroupHtml}", result)

if content == result:
    print("WARNING: JS regex missed!")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(result)
    print("Layout patched successfully!")
