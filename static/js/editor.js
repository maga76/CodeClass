// Редактор кода: Monaco (как в VS Code) из static/vendor; если он не загрузился — обычный textarea.

function enableTabKey(textarea) {
  // Tab вставляет 4 пробела, а не переключает фокус
  textarea.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab') return;
    event.preventDefault();
    const { selectionStart: start, selectionEnd: end, value } = textarea;
    textarea.value = value.slice(0, start) + '    ' + value.slice(end);
    textarea.selectionStart = textarea.selectionEnd = start + 4;
    textarea.dispatchEvent(new Event('input'));
  });
}

function mountMonaco(textarea) {
  if (typeof window.require === 'undefined' || !window.MONACO_VS) return;
  // Полный адрес, а не «/static/...»: фоновые обработчики Monaco не понимают относительные пути
  window.require.config({ paths: { vs: new URL(window.MONACO_VS, window.location.href).href } });
  window.require(['vs/editor/editor.main'], () => {
    const host = document.createElement('div');
    host.className = 'monaco-host';
    textarea.after(host);
    textarea.hidden = true;
    textarea.required = false;  // скрытое обязательное поле браузер не даёт отправить
    // Тема в цветах сайта
    monaco.editor.defineTheme('codeclass', {
      base: 'vs-dark',
      inherit: true,
      rules: [],
      colors: {
        'editor.background': '#0b111c',
        'editor.lineHighlightBackground': '#ffffff08',
        'editorLineNumber.foreground': '#475569',
        'editorLineNumber.activeForeground': '#94a3b8',
        'editorCursor.foreground': '#00d4ff',
        'editor.selectionBackground': '#00d4ff33',
      },
    });
    const editor = monaco.editor.create(host, {
      value: textarea.value,
      language: textarea.dataset.language,
      theme: 'codeclass',
      fontFamily: '"JetBrains Mono", Consolas, monospace',
      padding: { top: 14 },
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 14,
      tabSize: 4,
      scrollBeyondLastLine: false,
    });
    editor.onDidChangeModelContent(() => {
      textarea.value = editor.getValue();
      textarea.dispatchEvent(new Event('input'));
    });
  });
}

function bindPreview(textarea) {
  const preview = document.getElementById(textarea.dataset.preview);
  if (!preview) return;
  let timer;
  const update = () => { preview.srcdoc = textarea.value; };
  textarea.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(update, 300);
  });
  update();
}

function bindRunButton(textarea) {
  // «Запустить»: код выполняется на вводе ученика, результат не сохраняется и не оценивается
  const button = document.getElementById('run-button');
  if (!button) return;
  const form = textarea.form;
  button.addEventListener('click', async () => {
    const body = new FormData();
    body.append('csrfmiddlewaretoken', form.querySelector('[name=csrfmiddlewaretoken]').value);
    body.append('code', textarea.value);
    body.append('input', document.getElementById('run-input').value);
    const label = button.innerHTML;
    button.disabled = true;
    button.textContent = 'Выполняется…';
    let result;
    try {
      const response = await fetch(button.dataset.url, { method: 'POST', body });
      result = response.ok ? await response.json() : { verdict: `Ошибка сервера (${response.status})` };
    } catch {
      result = { verdict: 'Нет связи с сервером' };
    }
    button.disabled = false;
    button.innerHTML = label;
    document.getElementById('run-result').hidden = false;
    const verdict = document.getElementById('run-verdict');
    verdict.textContent = result.verdict;
    verdict.className = result.verdict === 'Выполнено' ? 'verdict-ok' : 'verdict-bad';
    document.getElementById('run-output').textContent = [result.output, result.error].filter(Boolean).join('\n') || ' ';
  });
}

document.querySelectorAll('textarea.code-editor').forEach((textarea) => {
  enableTabKey(textarea);
  bindPreview(textarea);
  bindRunButton(textarea);
  mountMonaco(textarea);
});
