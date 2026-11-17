document.addEventListener('DOMContentLoaded', () => {
  const category = document.querySelector('#category');
  const domainField = document.querySelector('#domain-field');
  const domain = document.querySelector('#domain');
  if (category && domainField && domain) {
    const updateDomain = () => {
      const technical = category.value === 'technical';
      domainField.hidden = !technical;
      domain.disabled = !technical;
      domain.required = technical;
    };
    category.addEventListener('change', updateDomain);
    window.addEventListener('pageshow', updateDomain);
    updateDomain();
  }
  document.querySelectorAll('form[data-loading-label]').forEach((form) => {
    const submitButton = form.querySelector('button[type="submit"]');
    if (!submitButton) return;
    const originalLabel = submitButton.innerHTML;
    let submitting = false;
    form.addEventListener('submit', (event) => {
      if (submitting || !form.checkValidity()) {
        event.preventDefault();
        if (!submitting) form.reportValidity();
        return;
      }
      submitting = true;
      submitButton.disabled = true;
      submitButton.textContent = form.dataset.loadingLabel;
      form.setAttribute('aria-busy', 'true');
    });
    window.addEventListener('pageshow', () => {
      submitting = false;
      submitButton.disabled = false;
      submitButton.innerHTML = originalLabel;
      form.removeAttribute('aria-busy');
    });
  });
  const answerBox = document.querySelector('#answer');
  if (answerBox) {
    const draftKey = answerBox.dataset && answerBox.dataset.draftKey;
    if (draftKey) {
      try {
        if (answerBox.readOnly) window.sessionStorage.removeItem(draftKey);
        else answerBox.value = window.sessionStorage.getItem(draftKey) || answerBox.value;
      } catch (_) { /* Storage may be disabled; server-saved answers still work. */ }
    }
    answerBox.addEventListener('input', () => {
      if (draftKey && !answerBox.readOnly) {
        try { window.sessionStorage.setItem(draftKey, answerBox.value); } catch (_) { /* Optional draft storage. */ }
      }
      answerBox.style.height = 'auto';
      answerBox.style.height = `${answerBox.scrollHeight}px`;
    });
  }
});
