import re

path = r"D:\projects_all_time\08 Intelligence to choose bw LLM & OCR\00 codes\doc-router\document-router-platform\static\app.js"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

new_func = """
        let logsHtml = '';
        let logsArray = job.debug_info ? job.debug_info.logs : null;
        if (logsArray && logsArray.length > 0) {
            const logsId = `logs-job-${job.id}`;
            logsHtml = `
                <div style="margin-top: 4px;">
                    <button class="debug-toggle" onclick="toggleDebug('${logsId}')" style="font-size: 0.7rem; padding: 2px 4px; color: var(--info);">
                        ▸ View Terminal Logs
                    </button>
                    <div class="debug-content" id="${logsId}" hidden style="background:#111827; color:#10B981; font-family:monospace; padding:8px; border-radius:4px; max-width: 300px; max-height: 150px; overflow: auto; white-space: pre-wrap; font-size: 0.65rem;">${escapeHtml(logsArray.join('\\n'))}</div>
                </div>
            `;
            // Remove logs so it doesn't double print
            delete job.debug_info.logs;
        }

        let debugHtml = "";
        if (job.debug_info && Object.keys(job.debug_info).length > 0) {
            const debugId = `debug-job-${job.id}`;
            debugHtml = `
                <div style="margin-top: 4px;">
                    <button class="debug-toggle" onclick="toggleDebug('${debugId}')" style="font-size: 0.7rem; padding: 2px 4px;">
                        ▸ Debug info
                    </button>
                    <div class="debug-content" id="${debugId}" hidden style="max-width: 300px; max-height: 150px; overflow: auto; white-space: pre-wrap; font-size: 0.7rem;">${escapeHtml(JSON.stringify(job.debug_info, null, 2))}</div>
                </div>
            `;
        }
"""

pattern = r"\s*let debugHtml = \"\";\s*if \(job\.debug_info\) \{\s*const debugId = `debug-job-\$\{job\.id\}`;\s*debugHtml = `.*?`;\s*\}"
result = re.sub(pattern, new_func, content, flags=re.DOTALL)

# Insert logsHtml in the rendering
result = result.replace("${debugHtml}", "${logsHtml}\n                    ${debugHtml}")

if content == result:
    print("WARNING: Regex did not match!")
else:
    with open(path, "w", encoding="utf-8") as f:
        f.write(result)
    print("Patched successfully")
