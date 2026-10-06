try { const t = localStorage.getItem('aeo-theme'); if (t) document.documentElement.setAttribute('data-theme', t); } catch (e) { /* noop */ }
