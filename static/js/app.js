/* Pokémon-Autovervollständigung für alle .pokemon-picker Elemente (nutzt /api/pokemon/?q=) */
(function () {
    'use strict';

    function debounce(fn, ms) {
        let t;
        return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
    }

    function initPicker(root) {
        const input = root.querySelector('.picker-input');
        const hidden = root.querySelector('.picker-value');
        const list = root.querySelector('.picker-results');
        const preview = root.querySelector('.picker-preview');
        let items = [];
        let active = -1;
        let controller;

        function close() { list.hidden = true; active = -1; }

        function choose(p) {
            input.value = p.name;
            hidden.value = p.identifier;
            preview.innerHTML = '';
            const img = document.createElement('img');
            img.src = p.sprite; img.alt = '';
            preview.appendChild(img);
            input.setCustomValidity('');
            close();
        }

        function highlight(i) {
            [...list.children].forEach((el, idx) => el.classList.toggle('active', idx === i));
            active = i;
            if (list.children[i]) list.children[i].scrollIntoView({ block: 'nearest' });
        }

        function render(results) {
            items = results;
            list.innerHTML = '';
            if (!results.length) {
                list.innerHTML = '<div class="list-group-item text-muted small">Keine Treffer</div>';
            }
            results.forEach((p, i) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'list-group-item list-group-item-action';
                const img = document.createElement('img');
                img.src = p.sprite; img.alt = ''; img.loading = 'lazy';
                const label = document.createElement('span');
                label.className = 'flex-grow-1';
                label.textContent = p.name;
                const num = document.createElement('small');
                num.className = 'text-muted';
                num.textContent = '#' + String(p.dex).padStart(4, '0');
                btn.append(img, label, num);
                btn.addEventListener('mousedown', (e) => { e.preventDefault(); choose(p); });
                btn.addEventListener('mouseenter', () => highlight(i));
                list.appendChild(btn);
            });
            list.hidden = false;
        }

        const search = debounce(async (q) => {
            if (controller) controller.abort();
            controller = new AbortController();
            try {
                const res = await fetch(`${window.POKEDEX_API}?q=${encodeURIComponent(q)}`, { signal: controller.signal });
                const data = await res.json();
                render(data.results);
            } catch (e) {
                if (e.name !== 'AbortError') console.error(e);
            }
        }, 180);

        input.addEventListener('input', () => {
            hidden.value = '';
            const q = input.value.trim();
            if (q.length < 1) { close(); return; }
            search(q);
        });
        input.addEventListener('keydown', (e) => {
            if (list.hidden || !items.length) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); highlight(Math.min(active + 1, items.length - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(Math.max(active - 1, 0)); }
            else if (e.key === 'Enter') { e.preventDefault(); choose(items[Math.max(active, 0)]); }
            else if (e.key === 'Escape') { close(); }
        });
        input.addEventListener('blur', () => setTimeout(close, 150));

        // Formular nur absenden, wenn wirklich ein Pokémon ausgewählt wurde
        const form = root.closest('form');
        if (form) {
            form.addEventListener('submit', (e) => {
                if (input.required && !hidden.value) {
                    e.preventDefault();
                    input.setCustomValidity('Bitte ein Pokémon aus der Liste wählen.');
                    input.reportValidity();
                }
            });
        }
    }

    document.querySelectorAll('.pokemon-picker').forEach(initPicker);
})();
