// ==UserScript==
// @name         Sprite Manager -> Gemini
// @namespace    merchants-rise
// @version      1.1
// @description  Takes sheets from the Sprite Manager (web_bridge.py): new chat, Pro without extended thinking, image and prompt, send.
// @match        https://gemini.google.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @run-at       document-idle
// @updateURL    http://127.0.0.1:47613/gemini_bridge.user.js
// @downloadURL  http://127.0.0.1:47613/gemini_bridge.user.js
// @noframes
// ==/UserScript==

/*
 * Gemini's page changes now and then; when a step stops working, the
 * selectors and names below are what to look at (Firefox: right-click the
 * element > Inspect). Every step reports to the Sprite Manager's status line.
 */
(function () {
    'use strict';

    const SERVER = 'http://127.0.0.1:47613';
    const POLL_MS = 1000;
    const STORE_KEY = 'spriteManagerJob';      // the sheet taken, kept over the reload into a new chat
    const MODEL = /\bpro\b/i;                  // the model menu entry to choose ("3.1 Pro")
    const THINKING = /extended thinking/i;     // the menu entry to switch off
    const EDITOR = 'rich-textarea [contenteditable="true"], div[contenteditable="true"][role="textbox"], .ql-editor[contenteditable="true"]';
    const SEND = 'button.send-button, button[aria-label*="Send" i], [data-test-id="send-button"]';
    const MENU_ITEMS = '[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], .mat-mdc-menu-item';
    const BUSY = '[role="progressbar"], mat-progress-spinner, mat-spinner, .loading, [class*="uploading" i]';

    let working = false;

    // --- talking to the Sprite Manager ----------------------------------

    function post(path, data) {
        return new Promise((resolve) => {
            GM_xmlhttpRequest({
                method: 'POST', url: SERVER + path, timeout: 5000,
                headers: {'Content-Type': 'application/json'},
                data: data ? JSON.stringify(data) : '',
                onload: (r) => resolve(r.status === 200 ? JSON.parse(r.responseText) : null),
                onerror: () => resolve(null), ontimeout: () => resolve(null),
            });
        });
    }

    function report(job, message, error = false) {
        console.log('[Sprite Manager]', message);
        toast(message, error);
        post('/status', {id: job.id, message, error});
    }

    function toast(message, error) {
        let box = document.getElementById('sprite-manager-toast');
        if (!box) {
            box = document.createElement('div');
            box.id = 'sprite-manager-toast';
            box.style.cssText = 'position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:99999;'
                + 'padding:8px 14px;border-radius:6px;font:14px sans-serif;color:#fff;pointer-events:none';
            document.body.appendChild(box);
        }
        box.textContent = 'Sprite Manager: ' + message;
        box.style.background = error ? '#a33' : '#3a5a3a';
        clearTimeout(box.hideTimer);
        box.hideTimer = setTimeout(() => box.remove(), error ? 15000 : 5000);
    }

    // --- the page ---------------------------------------------------------

    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

    async function waitFor(find, ms, what) {
        const until = Date.now() + ms;
        while (Date.now() < until) {
            const found = find();
            if (found) return found;
            await sleep(200);
        }
        throw new Error(`${what} not found`);
    }

    const visible = (el) => el && el.getClientRects().length > 0;
    const firstLine = (el) => (el.innerText || '').trim().split('\n')[0].trim();

    function click(el) {
        for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup']) {
            el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true}));
        }
        el.click();
    }

    function newChatPath() {
        const account = location.pathname.match(/^\/u\/\d+/);
        return (account ? account[0] : '') + '/app';
    }

    function inputArea(editor) {
        return editor.closest('input-area-v2, input-container, .input-area-container, .input-area, fieldset')
            || editor.parentElement.parentElement.parentElement;
    }

    // The button showing the model ("Pro") next to the microphone
    function modelButton() {
        const tagged = document.querySelector('[data-test-id="bard-mode-menu-button"] button, [data-test-id="bard-mode-menu-button"]');
        if (visible(tagged)) return tagged;
        return [...document.querySelectorAll('button[aria-haspopup], button.input-area-switch, bard-mode-switcher button')]
            .find((b) => visible(b) && /pro|flash|thinking|fast/i.test(b.innerText || b.getAttribute('aria-label') || ''));
    }

    function openMenuItems() {
        return [...document.querySelectorAll(MENU_ITEMS)].filter(visible);
    }

    async function openModelMenu() {
        const button = await waitFor(modelButton, 10000, 'The model button');
        click(button);
        await waitFor(() => openMenuItems().length > 0, 4000, 'The model menu');
        return openMenuItems();
    }

    async function closeMenu() {
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
        document.querySelector('.cdk-overlay-backdrop')?.click();
        await sleep(300);
    }

    function isOn(item) {
        const control = item.querySelector('[role="switch"], [aria-checked], input[type="checkbox"]') || item;
        if (control.matches('input[type="checkbox"]')) return control.checked;
        const checked = control.getAttribute('aria-checked') ?? item.getAttribute('aria-checked');
        if (checked !== null) return checked === 'true';
        return /checked|selected|active/i.test(control.className + ' ' + item.className)
            || !!item.querySelector('mat-icon[fonticon="check"], .check-icon, [data-mat-icon-name="check"]');
    }

    async function chooseModel(job) {
        let items = await openModelMenu();
        const pro = items.find((i) => MODEL.test(firstLine(i)) && !THINKING.test(firstLine(i)));
        if (!pro) {
            await closeMenu();
            throw new Error('no Pro entry in the model menu');
        }
        click(pro);   // choosing it again does no harm
        await sleep(600);
        // Extended thinking is a switch of its own in the same menu
        items = openMenuItems().length ? openMenuItems() : await openModelMenu();
        const thinking = items.find((i) => THINKING.test(i.innerText || ''));
        if (thinking && isOn(thinking)) {
            click(thinking);
            await sleep(600);
            report(job, 'extended thinking switched off');
        }
        await closeMenu();
    }

    function imageFile(job) {
        const bytes = Uint8Array.from(atob(job.image), (c) => c.charCodeAt(0));
        return new File([bytes], job.name, {type: 'image/png'});
    }

    const attachments = (area) => area.querySelectorAll('img, uploader-file-preview, .file-preview, [class*="attachment" i]').length;

    async function attachImage(editor, job) {
        const area = inputArea(editor);
        const before = attachments(area);
        const send = (make) => {
            const data = new DataTransfer();
            data.items.add(imageFile(job));
            make(data);
        };
        // Pasting is what a person does; dropping the file is the fallback
        send((data) => editor.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true})));
        try {
            await waitFor(() => attachments(area) > before, 4000, 'The pasted image');
            return;
        } catch (e) { /* try a drop */ }
        send((data) => {
            for (const type of ['dragenter', 'dragover', 'drop']) {
                editor.dispatchEvent(new DragEvent(type, {dataTransfer: data, bubbles: true, cancelable: true}));
            }
        });
        await waitFor(() => attachments(area) > before, 6000, 'The image in the chat box (paste and drop both failed)');
    }

    async function typePrompt(editor, prompt) {
        editor.focus();
        const selection = window.getSelection();
        selection.selectAllChildren(editor);
        selection.collapseToEnd();
        document.execCommand('insertText', false, prompt);
        await sleep(300);
        const start = prompt.trim().slice(0, 30);
        if ((editor.innerText || '').includes(start)) return;
        // Fall back to pasting the text
        const data = new DataTransfer();
        data.setData('text/plain', prompt);
        editor.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
        await waitFor(() => (editor.innerText || '').includes(start), 3000, 'The prompt in the chat box');
    }

    function sendButton(area) {
        const button = [...area.querySelectorAll(SEND)].concat([...document.querySelectorAll(SEND)]).find(visible);
        if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true') return null;
        return area.querySelector(BUSY) ? null : button;
    }

    // --- one sheet -----------------------------------------------------------

    async function run(job) {
        working = true;
        sessionStorage.removeItem(STORE_KEY);
        let step = 'the chat box';
        try {
            const editor = await waitFor(() => [...document.querySelectorAll(EDITOR)].find(visible), 20000, 'The chat box');
            step = 'choosing the model';
            let modelProblem = '';
            try {
                await chooseModel(job);
            } catch (e) {
                modelProblem = e.message;
            }
            step = 'the image';
            await attachImage(editor, job);
            step = 'the prompt';
            await typePrompt(editor, job.prompt);
            if (modelProblem) {
                report(job, `could not choose Pro (${modelProblem}) - image and prompt are in, choose the model and send by hand`, true);
                return;
            }
            step = 'sending';
            const button = await waitFor(() => sendButton(inputArea(editor)), 60000, 'An enabled send button');
            await sleep(300);
            click(button);
            report(job, `${job.label} sent with Pro - Ctrl+V the answer into the Sprite Manager when it is drawn`);
        } catch (e) {
            report(job, `stopped at ${step}: ${e.message}`, true);
        } finally {
            working = false;
        }
    }

    async function poll() {
        if (working) return;
        const kept = sessionStorage.getItem(STORE_KEY);
        if (kept) {
            run(JSON.parse(kept));
            return;
        }
        const job = await post('/take');
        if (!job) return;
        // Always a new chat: keep the sheet over the reload and go on there
        sessionStorage.setItem(STORE_KEY, JSON.stringify(job));
        working = true;
        report(job, `${job.label} taken - opening a new chat`);
        location.assign(newChatPath());
    }

    setInterval(poll, POLL_MS);
    poll();
})();
