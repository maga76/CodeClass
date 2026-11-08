// Уведомления исчезают сами через 5 секунд или по крестику
document.querySelectorAll('.toast').forEach((toast) => {
  const hide = () => {
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 300);
  };
  toast.querySelector('.toast-close').addEventListener('click', hide);
  // Важные сообщения (например, новый пароль ученика) не исчезают сами
  if (!toast.classList.contains('sticky')) setTimeout(hide, 5000);
});

// Кнопки «Скопировать»: data-copy="текст"
document.querySelectorAll('[data-copy]').forEach((button) => {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
    } catch {
      return;
    }
    const title = button.title;
    button.title = 'Скопировано!';
    button.classList.add('copied');
    setTimeout(() => { button.title = title; button.classList.remove('copied'); }, 1500);
  });
});

// Внутри программы для Windows (pywebview) показываем шестерёнку «Настройки программы»
function enableAppSettings() {
  if (!window.pywebview || !window.pywebview.api || !window.pywebview.api.open_settings) return;
  document.querySelectorAll('.app-settings[hidden]').forEach((button) => {
    button.hidden = false;
    button.addEventListener('click', () => window.pywebview.api.open_settings());
  });
}
window.addEventListener('pywebviewready', enableAppSettings);
enableAppSettings();
