document.addEventListener('DOMContentLoaded', () => {
  const answerBox = document.querySelector('#answer');
  if (answerBox) {
    answerBox.addEventListener('input', () => {
      answerBox.style.height = 'auto';
      answerBox.style.height = `${answerBox.scrollHeight}px`;
    });
  }
});
