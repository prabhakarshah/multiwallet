document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const btn = e.target.querySelector('button');
  const errorEl = document.getElementById('error');

  btn.disabled = true;
  btn.textContent = 'Signing in...';
  errorEl.innerHTML = '';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        username: document.getElementById('username').value,
        password: document.getElementById('password').value
      })
    });

    if (res.ok) {
      window.location.href = '/';
    } else {
      const data = await res.json();
      errorEl.innerHTML = `<div class="error">${data.detail || 'Login failed'}</div>`;
    }
  } catch (err) {
    errorEl.innerHTML = `<div class="error">Error: ${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Sign In';
  }
});
