/* Arena-Kampf: fragt den Zustand per Polling ab und schickt Aktionen an den Server. */
(function () {
    'use strict';
    var root = document.getElementById('arena');
    if (!root) return;

    var POLL_MS = 1500;
    var $ = function (id) { return document.getElementById(id); };
    var lastKey = null, sending = false, deadline = null, pollTimer = null, logCount = 0;

    function esc(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
        });
    }

    function hpClass(pct) { return pct > 50 ? 'bg-success' : pct > 20 ? 'bg-warning' : 'bg-danger'; }

    function types(mon) {
        return mon.types.map(function (t) {
            return '<span class="type-badge sm" style="--type-color:' + esc(t.color) + '">' + esc(t.name) + '</span>';
        }).join(' ');
    }

    function sideHtml(side, isYou) {
        var mon = side.mons[side.active];
        var roster = side.mons.map(function (m, i) {
            return '<img src="' + esc(m.sprite) + '" alt="' + esc(m.name) + '" title="' + esc(m.name) + ' (' + m.pct + ' %)" class="' +
                (m.fainted ? 'fainted ' : '') + (i === side.active ? 'current' : '') + '">';
        }).join('');
        return '<div class="card-body text-center">' +
            '<div class="d-flex justify-content-between align-items-center mb-2">' +
            '<span class="fw-bold">' + (isYou ? '<i class="bi bi-person-fill"></i> ' : '<i class="bi bi-person"></i> ') + esc(side.name) +
            (isYou ? ' <span class="small text-muted fw-normal">(du)</span>' : '') + '</span>' +
            '<span class="small text-muted">' + esc(side.team) + '</span></div>' +
            '<img class="arena-img' + (mon.fainted ? ' fainted' : '') + '" src="' + esc(mon.art) + '" alt="' + esc(mon.name) +
            '" onerror="this.onerror=null;this.src=\'' + esc(mon.sprite) + '\'">' +
            '<div class="h5 fw-bold mb-1">' + esc(mon.name) + '</div>' +
            '<div class="mb-2">' + types(mon) + '</div>' +
            '<div class="progress arena-hp"><div class="progress-bar ' + hpClass(mon.pct) + '" style="width:' + mon.pct + '%"></div></div>' +
            '<div class="small fw-semibold mt-1">' + (isYou ? mon.hp + ' / ' + mon.max_hp + ' KP' : mon.pct + ' % KP') + '</div>' +
            '<div class="arena-roster mt-2">' + roster + '</div></div>';
    }

    function actionsHtml(s) {
        if (s.status !== 'active') return '';
        if (!s.need_action) {
            return '<div class="text-center text-muted py-2"><div class="spinner-border spinner-border-sm text-danger me-2"></div>' +
                'Warte auf ' + esc(s.opp.name) + ' …</div>';
        }
        var you = s.you, mon = you.mons[you.active], html = '';
        if (s.forced) {
            html += '<h2 class="h6 fw-bold text-danger">' + esc(mon.name) + ' wurde besiegt – wähle dein nächstes Pokémon!</h2>';
        } else {
            html += '<h2 class="h6 fw-bold">Was soll ' + esc(mon.name) + ' tun?' +
                (s.opp_ready ? ' <span class="badge text-bg-warning">Gegner hat gewählt</span>' : '') + '</h2>' +
                '<div class="row row-cols-1 row-cols-sm-2 g-2 mb-3">';
            mon.moves.forEach(function (m, i) {
                html += '<div class="col"><button type="button" class="btn move-btn w-100" style="--type-color:' + esc(m.color) +
                    '" data-type="move" data-index="' + i + '"><span class="fw-bold d-block">' + esc(m.name) + '</span>' +
                    '<small>' + esc(m.type_name) + ' · ' + (m.cls === 'physical' ? 'Physisch' : 'Speziell') + ' · Stärke ' + m.power +
                    ' · ' + (m.acc ? m.acc + ' %' : 'trifft immer') + '</small></button></div>';
            });
            html += '</div>';
        }
        var bench = '';
        you.mons.forEach(function (m, i) {
            if (i === you.active || m.fainted) return;
            bench += '<button type="button" class="btn btn-outline-secondary switch-btn" data-type="switch" data-index="' + i + '">' +
                '<img src="' + esc(m.sprite) + '" alt=""> ' + esc(m.name) + ' <small class="text-muted">' + m.pct + ' %</small></button>';
        });
        if (bench) html += '<div class="small fw-semibold text-muted mb-1">Pokémon wechseln</div><div class="d-flex flex-wrap gap-2">' + bench + '</div>';
        return html;
    }

    function logHtml(log) {
        var html = '', turn = null;
        log.forEach(function (e) {
            if (e.t !== turn) {
                turn = e.t;
                html += '<div class="arena-log-turn">' + (turn === 0 ? 'Kampfbeginn' : 'Runde ' + turn) + '</div>';
            }
            html += '<div class="arena-log-line ' + esc(e.kind) + '">' + esc(e.text) + '</div>';
        });
        return html;
    }

    function resultHtml(s) {
        var r = s.result, title, cls;
        if (r.won === true) { title = '<i class="bi bi-trophy-fill text-warning"></i> Sieg!'; cls = 'winner'; }
        else if (r.won === false) { title = 'Niederlage'; cls = ''; }
        else { title = 'Unentschieden'; cls = ''; }
        var change = r.elo_change > 0 ? '+' + r.elo_change : String(r.elo_change);
        root.querySelector('#result').className = 'card border-0 shadow-sm mb-3 result-banner ' + cls;
        return '<div class="card-body text-center"><div class="h3 fw-bold mb-1">' + title + '</div>' +
            '<div class="text-muted mb-2">Entscheidung durch ' + esc(r.reason) + ' · Punkte: <strong class="' +
            (r.elo_change >= 0 ? 'text-success' : 'text-danger') + '">' + change + '</strong>' +
            (r.elo !== null ? ' → <strong>' + r.elo + '</strong>' : '') + '</div>' +
            '<a class="btn btn-danger" href="' + esc(root.dataset.lobbyUrl) + '"><i class="bi bi-arrow-repeat"></i> Zurück zur Arena</a></div>';
    }

    function render(s) {
        if (s.status === 'active' && s.seconds_left !== null) deadline = Date.now() + s.seconds_left * 1000;
        else deadline = null;

        var key = [s.status, s.v, s.need_action, s.opp_ready].join('|');
        if (key === lastKey) return;
        lastKey = key;

        $('waiting').hidden = s.status !== 'open';
        $('cancelled').hidden = s.status !== 'cancelled' || !!s.you;
        $('field').hidden = !s.you;
        $('result').hidden = !s.result;
        $('forfeitForm').hidden = !(s.status === 'open' || s.status === 'active');
        $('forfeitBtn').querySelector('span').textContent = s.status === 'open' ? 'Abbrechen' : 'Aufgeben';
        $('forfeitForm').dataset.question = s.status === 'open' ? 'Suche abbrechen?' : 'Wirklich aufgeben? Das zählt als Niederlage.';

        if (s.status === 'open') {
            $('waitingText').textContent = s.invited ? 'Warte, bis ' + s.invited + ' die Herausforderung annimmt …' : 'Suche Gegner …';
        }
        if (s.you) {
            $('turnInfo').textContent = s.status === 'active' ? 'Runde ' + s.turn : 'Beendet';
            $('youSide').innerHTML = sideHtml(s.you, true);
            $('oppSide').innerHTML = sideHtml(s.opp, false);
            $('actions').innerHTML = actionsHtml(s);
            $('actionCard').hidden = s.status !== 'active';
            var log = $('log');
            log.innerHTML = logHtml(s.log);
            if (s.log.length !== logCount) { log.scrollTop = log.scrollHeight; logCount = s.log.length; }
        }
        if (s.result) $('result').innerHTML = resultHtml(s);
        if (s.status === 'finished' || s.status === 'cancelled') { clearInterval(pollTimer); $('timer').hidden = true; }
    }

    function poll() {
        if (sending) return;
        fetch(root.dataset.stateUrl, {credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (s) { if (s && !sending) render(s); })
            .catch(function () {});
    }

    function act(type, index) {
        if (sending) return;
        sending = true;
        root.querySelectorAll('#actions button').forEach(function (b) { b.disabled = true; });
        fetch(root.dataset.actionUrl, {
            method: 'POST', credentials: 'same-origin',
            headers: {'X-CSRFToken': root.dataset.csrf, 'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'type=' + encodeURIComponent(type) + '&index=' + encodeURIComponent(index)
        }).then(function (r) { return r.json(); })
            .then(function (s) { sending = false; lastKey = null; render(s); })
            .catch(function () { sending = false; lastKey = null; poll(); });
    }

    $('actions').addEventListener('click', function (e) {
        var btn = e.target.closest('button[data-type]');
        if (btn) act(btn.dataset.type, btn.dataset.index);
    });

    setInterval(function () {
        var t = $('timer');
        if (deadline === null) { t.hidden = true; return; }
        var left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
        t.hidden = false;
        t.textContent = left + ' s';
        t.className = 'badge ' + (left <= 10 ? 'text-bg-danger' : 'text-bg-secondary');
    }, 500);

    poll();
    pollTimer = setInterval(poll, POLL_MS);
})();
