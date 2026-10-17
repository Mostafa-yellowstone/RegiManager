/* RegiManager public assistant widget: text chat, dictation and hands-free voice conversation (browser speech, free). */
(function () {
    'use strict';

    var root = document.getElementById('rm-assistant');
    if (!root) return;

    var LANGS = {
        en: { native: 'English', speech: 'en-US', hello: "Hi, I'm Regi! I can explain registrations, renewals, plate transfers, titles, TLC renewals and insurance. What would you like to know?" },
        es: { native: 'Español', speech: 'es-US', hello: '¡Hola, soy Regi! Puedo explicarte registros, renovaciones, transferencia de placas, títulos, renovaciones de TLC y seguros. ¿Qué te gustaría saber?' },
        ar: { native: 'العربية', speech: 'ar-EG', rtl: true, hello: 'مرحباً، أنا ريجي! أستطيع شرح تسجيل المركبات وتجديده ونقل اللوحات واستخراج الملكية وتجديد رخص TLC والتأمين. ماذا تريد أن تعرف؟' },
        zh: { native: '中文', speech: 'zh-CN', hello: '你好！我可以讲解车辆注册、续期、车牌转移、产权证、TLC 续期和保险。你想了解什么？' },
        ru: { native: 'Русский', speech: 'ru-RU', hello: 'Здравствуйте! Я расскажу о регистрации, продлении, переносе номеров, титулах, продлении TLC и страховке. Что вас интересует?' },
        bn: { native: 'বাংলা', speech: 'bn-IN', hello: 'নমস্কার! আমি রেজিস্ট্রেশন, রিনিউয়াল, প্লেট ট্রান্সফার, টাইটেল, TLC রিনিউয়াল ও ইনস্যুরেন্স বুঝিয়ে বলতে পারি। আপনি কী জানতে চান?' },
        ht: { native: 'Kreyòl ayisyen', speech: 'fr-FR', hello: 'Bonjou! Mwen ka eksplike w enskripsyon machin, renouvèlman, transfè plak, tit, renouvèlman TLC ak asirans. Kisa ou vle konnen?' },
        fr: { native: 'Français', speech: 'fr-FR', hello: "Bonjour ! J'explique les immatriculations, renouvellements, transferts de plaques, titres, renouvellements TLC et assurances. Que voulez-vous savoir ?" },
        ko: { native: '한국어', speech: 'ko-KR', hello: '안녕하세요! 차량 등록, 갱신, 번호판 이전, 타이틀, TLC 갱신, 보험에 대해 설명해 드립니다. 무엇이 궁금하세요?' },
        pl: { native: 'Polski', speech: 'pl-PL', hello: 'Cześć! Wyjaśnię rejestrację, odnowienia, przeniesienie tablic, tytuły własności, odnowienia TLC i ubezpieczenia. Co chcesz wiedzieć?' },
        ur: { native: 'اردو', speech: 'ur-PK', rtl: true, hello: 'السلام علیکم! میں رجسٹریشن، تجدید، پلیٹ ٹرانسفر، ٹائٹل، TLC تجدید اور انشورنس کے بارے میں بتا سکتا ہوں۔ آپ کیا جاننا چاہتے ہیں؟' },
        hi: { native: 'हिन्दी', speech: 'hi-IN', hello: 'नमस्ते! मैं रजिस्ट्रेशन, रिन्यूअल, प्लेट ट्रांसफर, टाइटल, TLC रिन्यूअल और इंश्योरेंस समझा सकता हूँ। आप क्या जानना चाहते हैं?' },
        pt: { native: 'Português', speech: 'pt-BR', hello: 'Olá! Posso explicar registros, renovações, transferência de placas, títulos, renovações da TLC e seguros. O que você quer saber?' },
        it: { native: 'Italiano', speech: 'it-IT', hello: 'Ciao! Posso spiegarti immatricolazioni, rinnovi, trasferimento targhe, titoli di proprietà, rinnovi TLC e assicurazioni. Cosa vuoi sapere?' },
        tr: { native: 'Türkçe', speech: 'tr-TR', hello: 'Merhaba! Araç kaydı, yenileme, plaka transferi, tapu (title), TLC yenileme ve sigorta konularını anlatabilirim. Ne öğrenmek istersiniz?' },
        uk: { native: 'Українська', speech: 'uk-UA', hello: 'Вітаю! Я поясню реєстрацію, продовження, перенесення номерів, титули, продовження TLC і страхування. Що вас цікавить?' },
        yi: { native: 'ייִדיש', speech: 'he-IL', rtl: true },
        el: { native: 'Ελληνικά', speech: 'el-GR', hello: 'Γεια σας! Εξηγώ ταξινομήσεις, ανανεώσεις, μεταφορά πινακίδων, τίτλους, ανανεώσεις TLC και ασφάλειες. Τι θέλετε να μάθετε;' },
        pa: { native: 'ਪੰਜਾਬੀ', speech: 'pa-IN' },
        de: { native: 'Deutsch', speech: 'de-DE', hello: 'Hallo! Ich erkläre Zulassung, Verlängerung, Kennzeichenübertragung, Fahrzeugbrief (Title), TLC-Verlängerung und Versicherung. Was möchten Sie wissen?' },
    };

    var SUGGESTIONS = [
        'How do I renew my vehicle registration?',
        'How do I transfer my plates to a new car?',
        'How do I get a title or replace a lost one?',
        'How do I renew my TLC vehicle or driver license?',
        'What do I need to register a car from another state?',
        'What happens if my insurance lapses?',
    ];

    var STORE_KEY = 'rma-conversation';
    var LANG_KEY = 'rma-language';
    var endpoint = root.dataset.endpoint;
    var launcher = root.querySelector('.rma-launcher');
    var panel = root.querySelector('.rma-panel');
    var langScreen = root.querySelector('.rma-lang-screen');
    var chat = root.querySelector('.rma-chat');
    var list = root.querySelector('.rma-messages');
    var suggestions = root.querySelector('.rma-suggestions');
    var form = root.querySelector('.rma-input');
    var input = form.querySelector('textarea');
    var sendBtn = form.querySelector('.rma-send-btn');
    var micBtn = form.querySelector('.rma-mic-btn');
    var callBtn = form.querySelector('.rma-call-btn');
    var callbar = root.querySelector('.rma-callbar');
    var callStatus = root.querySelector('.rma-call-status');
    var langLabel = root.querySelector('.rma-lang-label');

    var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    var synth = window.speechSynthesis;
    var state = loadState();
    var busy = false;
    var inCall = false;
    var recognizer = null;

    function loadState() {
        try {
            var saved = JSON.parse(sessionStorage.getItem(STORE_KEY) || 'null');
            if (saved && Array.isArray(saved.messages)) return saved;
        } catch (e) { /* ignore */ }
        return { lang: localStorage.getItem(LANG_KEY) || '', messages: [] };
    }

    function saveState() {
        try {
            sessionStorage.setItem(STORE_KEY, JSON.stringify({ lang: state.lang, messages: state.messages.slice(-30) }));
            if (state.lang) localStorage.setItem(LANG_KEY, state.lang);
        } catch (e) { /* storage full or blocked */ }
    }

    function csrfToken() {
        var field = root.querySelector('input[name=csrfmiddlewaretoken]');
        var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : (field ? field.value : '');
    }

    function lang() { return LANGS[state.lang] || LANGS.en; }

    function escapeHtml(text) {
        return String(text).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function inline(text) {
        var html = escapeHtml(text);
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
        html = html.replace(/(^|[\s(])((?:https?:\/\/)?(?:www\.)?(?:[a-z0-9-]+\.)+(?:gov|com|org|net|ny\.us)(?:\/[^\s<)]*)?)/gi, function (m, pre, url) {
            if (/^\d/.test(url)) return m;
            var href = /^https?:\/\//i.test(url) ? url : 'https://' + url;
            return pre + '<a href="' + href + '" target="_blank" rel="noopener noreferrer">' + url + '</a>';
        });
        html = html.replace(/(^|[\s(])(\/contact\/)/g, '$1<a href="/contact/">$2</a>');
        return html;
    }

    function renderMarkdown(text) {
        var out = [];
        var listType = null;
        String(text).split(/\r?\n/).forEach(function (line) {
            var bullet = line.match(/^\s*[-*•]\s+(.*)$/);
            var numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
            var heading = line.match(/^\s*#{1,4}\s+(.*)$/);
            var type = bullet ? 'ul' : numbered ? 'ol' : null;
            if (listType && type !== listType) { out.push('</' + listType + '>'); listType = null; }
            if (type) {
                if (!listType) { out.push('<' + type + '>'); listType = type; }
                out.push('<li>' + inline((bullet || numbered)[1]) + '</li>');
            } else if (heading) {
                out.push('<p><strong>' + inline(heading[1]) + '</strong></p>');
            } else if (line.trim()) {
                out.push('<p>' + inline(line) + '</p>');
            }
        });
        if (listType) out.push('</' + listType + '>');
        return out.join('');
    }

    function plainForSpeech(text) {
        return String(text)
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
            .replace(/[*#`_>]/g, '')
            .replace(/https?:\/\//g, '')
            .replace(/\s+/g, ' ')
            .trim();
    }

    function addBubble(role, text, opts) {
        var bubble = document.createElement('div');
        bubble.className = 'rma-msg rma-msg--' + role + (opts && opts.error ? ' rma-msg--error' : '');
        if (lang().rtl) bubble.dir = 'rtl';
        if (role === 'assistant') {
            bubble.innerHTML = renderMarkdown(text);
            if (synth && !(opts && opts.noSpeak)) {
                var speak = document.createElement('button');
                speak.type = 'button';
                speak.className = 'rma-speak';
                speak.textContent = '🔊';
                speak.title = 'Listen';
                speak.setAttribute('aria-label', 'Read this answer aloud');
                speak.addEventListener('click', function () { speakText(text); });
                bubble.appendChild(speak);
            }
        } else {
            bubble.textContent = text;
        }
        list.appendChild(bubble);
        list.scrollTop = list.scrollHeight;
        return bubble;
    }

    function showTyping() {
        var el = document.createElement('div');
        el.className = 'rma-msg rma-msg--assistant rma-typing';
        el.innerHTML = '<span></span><span></span><span></span>';
        list.appendChild(el);
        list.scrollTop = list.scrollHeight;
        return el;
    }

    function renderSuggestions() {
        suggestions.innerHTML = '';
        if (state.messages.length > 1) return;
        SUGGESTIONS.forEach(function (q) {
            var chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'rma-chip';
            chip.textContent = q;
            chip.addEventListener('click', function () { send(q); });
            suggestions.appendChild(chip);
        });
    }

    function renderConversation() {
        list.innerHTML = '';
        if (!state.messages.length) {
            var hello = lang().hello || LANGS.en.hello;
            state.messages.push({ role: 'assistant', content: hello, greeting: true });
        }
        state.messages.forEach(function (m) { addBubble(m.role, m.content, { noSpeak: m.greeting }); });
        renderSuggestions();
        langLabel.textContent = lang().native;
        input.dir = lang().rtl ? 'rtl' : 'auto';
    }

    function showLanguageScreen() {
        stopCall();
        langScreen.hidden = false;
        chat.hidden = true;
        var first = langScreen.querySelector('.rma-lang-option');
        if (first) first.focus();
    }

    function chooseLanguage(code) {
        var changed = code !== state.lang;
        state.lang = code;
        if (changed) state.messages = [];
        saveState();
        langScreen.hidden = true;
        chat.hidden = false;
        renderConversation();
        input.focus();
    }

    function openPanel() {
        panel.hidden = false;
        root.classList.add('rma--open');
        launcher.setAttribute('aria-expanded', 'true');
        if (!state.lang) showLanguageScreen();
        else { langScreen.hidden = true; chat.hidden = false; renderConversation(); input.focus(); }
    }

    function closePanel() {
        stopCall();
        if (synth) synth.cancel();
        panel.hidden = true;
        root.classList.remove('rma--open');
        launcher.setAttribute('aria-expanded', 'false');
        launcher.focus();
    }

    function setBusy(value) {
        busy = value;
        sendBtn.disabled = value;
        input.disabled = value && !inCall;
    }

    function send(text) {
        text = String(text || '').trim();
        if (!text || busy) return Promise.resolve();
        if (synth) synth.cancel();
        state.messages = state.messages.filter(function (m) { return !m.greeting; });
        state.messages.push({ role: 'user', content: text });
        saveState();
        addBubble('user', text);
        suggestions.innerHTML = '';
        input.value = '';
        autoGrow();
        setBusy(true);
        if (inCall) callStatus.textContent = 'Thinking…';
        var typing = showTyping();
        var payload = {
            language: state.lang || 'en',
            messages: state.messages.slice(-12).map(function (m) { return { role: m.role, content: m.content }; }),
        };
        return fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify(payload),
            credentials: 'same-origin',
        }).then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (data) { return { res: res, data: data }; });
        }).then(function (result) {
            typing.remove();
            var reply = result.data.reply || result.data.error || 'Something went wrong. Please try again.';
            if (result.res.ok && result.data.ok) {
                state.messages.push({ role: 'assistant', content: reply });
                saveState();
                addBubble('assistant', reply);
                if (inCall) speakText(reply, listen);
            } else {
                addBubble('assistant', reply, { error: true, noSpeak: true });
                if (inCall) speakText(reply, listen);
            }
        }, function () {
            typing.remove();
            var msg = navigator.onLine === false ? "You're offline. Reconnect and ask again." : "Couldn't reach the assistant. Please try again.";
            addBubble('assistant', msg, { error: true, noSpeak: true });
            if (inCall) stopCall();
        }).then(function () { setBusy(false); if (!inCall) input.focus(); });
    }

    function pickVoice(code) {
        if (!synth) return null;
        var voices = synth.getVoices();
        var base = code.split('-')[0];
        return voices.find(function (v) { return v.lang === code; })
            || voices.find(function (v) { return v.lang && v.lang.split(/[-_]/)[0] === base; })
            || null;
    }

    function speakText(text, onDone) {
        if (!synth) { if (onDone) onDone(); return; }
        synth.cancel();
        var code = lang().speech;
        var voice = pickVoice(code);
        // Chrome stops long utterances after ~15s, so speak sentence by sentence.
        var chunks = plainForSpeech(text).match(/[^.!?。！？؟]+[.!?。！？؟]*\s*/g) || [plainForSpeech(text)];
        if (inCall) callStatus.textContent = 'Speaking… (tap End call to stop)';
        chunks.forEach(function (chunk, index) {
            var utter = new SpeechSynthesisUtterance(chunk.trim());
            utter.lang = code;
            if (voice) utter.voice = voice;
            utter.rate = 1;
            if (index === chunks.length - 1) {
                utter.onend = function () { if (onDone) onDone(); };
                utter.onerror = function () { if (onDone) onDone(); };
            }
            synth.speak(utter);
        });
    }

    function makeRecognizer() {
        var r = new Recognition();
        r.lang = lang().speech;
        r.interimResults = true;
        r.maxAlternatives = 1;
        r.continuous = false;
        return r;
    }

    function dictate() {
        if (!Recognition || busy) return;
        var r = makeRecognizer();
        var finalText = '';
        micBtn.classList.add('rma-recording');
        r.onresult = function (event) {
            var interim = '';
            for (var i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) finalText += event.results[i][0].transcript;
                else interim += event.results[i][0].transcript;
            }
            input.value = (finalText + interim).trim();
            autoGrow();
        };
        r.onerror = function (event) {
            if (event.error === 'not-allowed') addBubble('assistant', 'Microphone access was blocked. Allow the microphone in your browser to talk.', { error: true, noSpeak: true });
        };
        r.onend = function () {
            micBtn.classList.remove('rma-recording');
            if (finalText.trim()) send(finalText);
        };
        r.start();
    }

    function listen() {
        if (!inCall) return;
        recognizer = makeRecognizer();
        var heard = '';
        callStatus.textContent = 'Listening… speak now';
        recognizer.onresult = function (event) {
            var interim = '';
            for (var i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) heard += event.results[i][0].transcript;
                else interim += event.results[i][0].transcript;
            }
            callStatus.textContent = '“' + (heard + interim).trim() + '”';
        };
        recognizer.onerror = function (event) {
            if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
                addBubble('assistant', 'Microphone access was blocked. Allow the microphone in your browser to use voice.', { error: true, noSpeak: true });
                stopCall();
            }
        };
        recognizer.onend = function () {
            recognizer = null;
            if (!inCall) return;
            if (heard.trim()) send(heard);
            else setTimeout(listen, 250);
        };
        try { recognizer.start(); } catch (e) { setTimeout(listen, 500); }
    }

    function startCall() {
        if (!Recognition) return;
        inCall = true;
        callbar.hidden = false;
        callBtn.classList.add('rma-active');
        root.classList.add('rma--calling');
        if (synth) synth.getVoices();
        listen();
    }

    function stopCall() {
        if (!inCall) return;
        inCall = false;
        callbar.hidden = true;
        callBtn.classList.remove('rma-active');
        root.classList.remove('rma--calling');
        if (recognizer) { try { recognizer.abort(); } catch (e) { /* already stopped */ } recognizer = null; }
        if (synth) synth.cancel();
    }

    function autoGrow() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 140) + 'px';
    }

    root.querySelectorAll('.rma-lang-option').forEach(function (btn) {
        var info = LANGS[btn.dataset.lang] || {};
        btn.innerHTML = '<span class="rma-lang-native">' + escapeHtml(info.native || btn.dataset.name) + '</span>'
            + '<span class="rma-lang-en">' + escapeHtml(btn.dataset.name) + '</span>';
        btn.addEventListener('click', function () { chooseLanguage(btn.dataset.lang); });
    });

    launcher.addEventListener('click', function () { if (panel.hidden) openPanel(); else closePanel(); });
    root.querySelector('.rma-close-btn').addEventListener('click', closePanel);
    root.querySelector('.rma-lang-btn').addEventListener('click', showLanguageScreen);
    root.querySelector('.rma-new-btn').addEventListener('click', function () {
        stopCall();
        state.messages = [];
        saveState();
        if (state.lang) { langScreen.hidden = true; chat.hidden = false; renderConversation(); }
    });
    root.querySelector('.rma-end-call').addEventListener('click', stopCall);
    form.addEventListener('submit', function (event) { event.preventDefault(); send(input.value); });
    input.addEventListener('input', autoGrow);
    input.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(input.value); }
    });
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && !panel.hidden) closePanel(); });

    if (Recognition) {
        micBtn.hidden = false;
        callBtn.hidden = false;
        micBtn.addEventListener('click', dictate);
        callBtn.addEventListener('click', function () { if (inCall) stopCall(); else startCall(); });
    }
    if (synth && synth.onvoiceschanged !== undefined) synth.onvoiceschanged = function () { synth.getVoices(); };
})();
