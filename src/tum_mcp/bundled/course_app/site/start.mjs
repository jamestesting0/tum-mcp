import('./app.mjs').catch(() => {
  const root = document.querySelector('#app');
  const main = document.createElement('main'); main.className = 'reading';
  const title = document.createElement('h1'); title.textContent = 'Course unavailable';
  const message = document.createElement('p'); message.setAttribute('role', 'alert');
  message.textContent = 'The course could not load. Reload to try again. If this continues, the site needs to be rebuilt.';
  const reload = document.createElement('button'); reload.type = 'button';
  reload.className = 'primary'; reload.textContent = 'Reload course';
  reload.addEventListener('click', () => location.reload());
  main.append(title, message, reload); root.replaceChildren(main);
});
