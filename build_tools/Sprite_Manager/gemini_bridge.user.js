// ==UserScript==
// @name         Sprite Manager -> Gemini
// @namespace    merchants-rise
// @version      1.6
// @description  Takes sheets from the Sprite Manager (web_bridge.py): new chat, high thinking level, image and prompt, send, then download the answer's image.
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
    const THINKING = /^thinking level/i;       // the model menu entry opening the levels
    const LEVEL = /^high$/i;                   // the level to choose
    const EDITOR = 'rich-textarea [contenteditable="true"], div[contenteditable="true"][role="textbox"], .ql-editor[contenteditable="true"]';
    const SEND = 'button.send-button, button[aria-label*="Send" i], [data-test-id="send-button"]';
    const MENU_ITEMS = '[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"], .mat-mdc-menu-item';
    const BUSY = '[role="progressbar"], mat-progress-spinner, mat-spinner, .loading, [class*="uploading" i]';
    const STOP = 'button[aria-label*="stop" i], button.stop';   // shown while Gemini is still answering
    const NOT_ANSWER = 'user-query, rich-textarea, uploader-file-preview, input-area-v2';   // our own image is in these
    const ANSWER_WAIT_MS = 10 * 60 * 1000;     // how long an answer may take to be drawn
    const NO_IMAGE_MS = 20000;                 // answered, nothing stopping any more, and no image this long: give up

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

    function report(job, message, error = false, extra = {}) {
        console.log('[Sprite Manager]', message);
        toast(message, error);
        return post('/status', {id: job.id, message, error, ...extra});
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
            await sleep(100);
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

    // The chat box as it is now: Gemini swaps it for a new one while a chat loads, so never keep one
    function chatBox() {
        return [...document.querySelectorAll(EDITOR)].find((el) => el.isConnected && visible(el)) || null;
    }

    // Wait until the same chat box has stayed put for a moment, i.e. the page is done building it
    async function settledChatBox() {
        const until = Date.now() + 20000;
        let last = null;
        let since = 0;
        while (Date.now() < until) {
            const box = chatBox();
            if (box !== last) {
                last = box;
                since = Date.now();
            } else if (box && Date.now() - since >= 400) {
                return box;
            }
            await sleep(100);
        }
        throw new Error('The chat box not found');
    }

    function inputArea() {
        const editor = chatBox();
        if (!editor) return document.body;
        const tagged = editor.closest('input-area-v2, input-container, .input-area-container, .input-area, fieldset');
        if (tagged) return tagged;
        let area = editor;
        for (let i = 0; i < 3 && area.parentElement; i++) area = area.parentElement;
        return area;
    }

    // The button showing the model ("Gemini Auto") next to the microphone
    function modelButton() {
        const tagged = document.querySelector('[data-test-id="bard-mode-menu-button"] button, [data-test-id="bard-mode-menu-button"]');
        if (visible(tagged)) return tagged;
        return [...document.querySelectorAll('button[aria-haspopup], button.input-area-switch, bard-mode-switcher button')]
            .find((b) => visible(b) && /gemini|auto|pro|flash|thinking|fast/i.test(b.innerText || b.getAttribute('aria-label') || ''));
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
        await sleep(100);
    }

    function isOn(item) {
        const control = item.querySelector('[role="switch"], [aria-checked], input[type="checkbox"]') || item;
        if (control.matches('input[type="checkbox"]')) return control.checked;
        const checked = control.getAttribute('aria-checked') ?? item.getAttribute('aria-checked');
        if (checked !== null) return checked === 'true';
        return /checked|selected|active/i.test(control.className + ' ' + item.className)
            || !!item.querySelector('mat-icon[fonticon="check"], .check-icon, [data-mat-icon-name="check"]');
    }

    async function chooseThinkingLevel(job) {
        const items = await openModelMenu();
        const thinking = items.find((i) => THINKING.test(firstLine(i)));
        if (!thinking) {
            await closeMenu();
            throw new Error('no "Thinking level" entry in the model menu');
        }
        // The levels are a submenu of their own, opened by hovering or clicking the entry
        thinking.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
        click(thinking);
        let high;
        try {
            high = await waitFor(() => openMenuItems().find((i) => LEVEL.test(firstLine(i))), 3000, 'The "High" thinking level');
        } catch (e) {
            await closeMenu();
            throw e;
        }
        if (!isOn(high)) {
            click(high);
            await sleep(150);
            report(job, 'thinking level set to High');
        }
        await closeMenu();
    }

    function imageFile(job) {
        const bytes = Uint8Array.from(atob(job.image), (c) => c.charCodeAt(0));
        return new File([bytes], job.name, {type: 'image/png'});
    }

    const attachments = (area) => area.querySelectorAll('img, uploader-file-preview, .file-preview, [class*="attachment" i]').length;

    async function attachImage(job) {
        const before = attachments(inputArea());
        const send = (make) => {
            const data = new DataTransfer();
            data.items.add(imageFile(job));
            make(data);
        };
        // Pasting is what a person does; dropping the file is the fallback
        send((data) => chatBox().dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true})));
        try {
            await waitFor(() => attachments(inputArea()) > before, 4000, 'The pasted image');
            return;
        } catch (e) { /* try a drop */ }
        send((data) => {
            const editor = chatBox();
            for (const type of ['dragenter', 'dragover', 'drop']) {
                editor.dispatchEvent(new DragEvent(type, {dataTransfer: data, bubbles: true, cancelable: true}));
            }
        });
        await waitFor(() => attachments(inputArea()) > before, 6000, 'The image in the chat box (paste and drop both failed)');
    }

    async function typePrompt(prompt) {
        const editor = await waitFor(chatBox, 5000, 'The chat box');
        editor.focus();
        const selection = window.getSelection();
        selection.selectAllChildren(editor);
        selection.collapseToEnd();
        document.execCommand('insertText', false, prompt);
        await sleep(100);
        const start = prompt.trim().slice(0, 30);
        const typed = () => (chatBox()?.innerText || '').includes(start);
        if (typed()) return;
        // Fall back to pasting the text
        const data = new DataTransfer();
        data.setData('text/plain', prompt);
        chatBox().dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
        await waitFor(typed, 3000, 'The prompt in the chat box');
    }

    function sendButton(area) {
        const button = [...area.querySelectorAll(SEND)].concat([...document.querySelectorAll(SEND)]).find(visible);
        if (!button || button.disabled || button.getAttribute('aria-disabled') === 'true') return null;
        return area.querySelector(BUSY) ? null : button;
    }

    // --- the answer ------------------------------------------------------

    // A button's names: label, tooltip, test id, text and its icon's name ("download")
    const buttonNames = (b) => [b.getAttribute('aria-label'), b.getAttribute('mattooltip'), b.title,
        b.getAttribute('data-test-id'), b.innerText,
        ...[...b.querySelectorAll('mat-icon, [fonticon], [data-mat-icon-name]')].map((i) =>
            [i.getAttribute('fonticon'), i.getAttribute('data-mat-icon-name'), i.textContent].join(' '))]
        .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
    const MORE = /\bmore(\b|_)/i;              // the "More" button (three dots) under an answer
    const DOWNLOAD_ITEM = /download image/i;   // its menu entry downloading the image in full size
    const SEARCH_LEVELS = 15;                  // how far up from the image the "More" button is looked for

    // The drawn images in the answer: big, loaded, and not our own upload
    const answerImages = () => [...document.querySelectorAll('img')]
        .filter((img) => img.complete && img.naturalWidth >= 256 && !img.closest(NOT_ANSWER));

    // The "More" button of the answer an image is in: the nearest one going up from the image
    function moreButton(img) {
        let area = img;
        for (let i = 0; i < SEARCH_LEVELS && area.parentElement; i++) {
            area = area.parentElement;
            const found = [...area.querySelectorAll('button, [role="button"]')].filter((b) => MORE.test(buttonNames(b)));
            if (found.length) return found[found.length - 1];
        }
        return null;
    }

    // What there is under an image whose "More" button was not found, for fixing the selectors
    function describeAround(img) {
        let area = img;
        for (let i = 0; i < SEARCH_LEVELS && area.parentElement; i++) area = area.parentElement;
        const names = [...area.querySelectorAll('button, [role="button"]')].map(buttonNames).filter(Boolean);
        return `buttons near the image: ${names.length ? names.map((n) => `"${n.slice(0, 40)}"`).join(', ') : 'none'}`;
    }

    // Open the answer's "More" menu and find "Download image" in it
    async function downloadEntry(more) {
        click(more);
        try {
            return await waitFor(() => openMenuItems().find((i) => DOWNLOAD_ITEM.test(i.innerText || '')),
                3000, 'The "Download image" entry of the "More" menu');
        } catch (e) {
            const seen = openMenuItems().map(firstLine);
            await closeMenu();
            throw new Error(`${e.message} (menu: ${seen.length ? seen.join(', ') : 'did not open'})`);
        }
    }

    // Gemini takes anything from seconds to minutes, so look once a second until the image is there
    async function downloadAnswer(job) {
        const until = Date.now() + ANSWER_WAIT_MS;
        let stopSeen = false;
        let quietSince = 0;
        let imageSince = 0;
        while (Date.now() < until) {
            const images = answerImages();
            // The buttons under the answer come once it is finished; the newest answer is the last
            const more = images.length ? moreButton(images[images.length - 1]) : null;
            if (more) {
                const entry = await downloadEntry(more);
                // Told first, so the Sprite Manager knows what is in Downloads before the file is
                await report(job, `${job.label} drawn - downloading it`, false, {download: true});
                click(entry);
                return;
            }
            if (images.length) {
                imageSince = imageSince || Date.now();
                if (Date.now() - imageSince > NO_IMAGE_MS) {
                    console.log('[Sprite Manager] the image without a "More" button:', images);
                    throw new Error(`the image is there but its "More" button was not found - download it by hand (${describeAround(images[images.length - 1])})`);
                }
            } else {
                // An answer without an image: only trusted once the stop button has been seen to come and go
                const stopping = [...document.querySelectorAll(STOP)].some(visible);
                stopSeen = stopSeen || stopping;
                quietSince = stopping || !stopSeen ? 0 : (quietSince || Date.now());
                if (quietSince && Date.now() - quietSince > NO_IMAGE_MS) {
                    throw new Error('Gemini answered without an image - have a look at the tab');
                }
            }
            await sleep(1000);
        }
        throw new Error('no image after 10 minutes');
    }

    // --- one sheet -----------------------------------------------------------

    async function run(job) {
        working = true;
        sessionStorage.removeItem(STORE_KEY);
        let step = 'the chat box';
        try {
            await settledChatBox();
            step = 'the thinking level';
            let modelProblem = '';
            try {
                await chooseThinkingLevel(job);
            } catch (e) {
                modelProblem = e.message;
            }
            step = 'the image';
            await attachImage(job);
            step = 'the prompt';
            await typePrompt(job.prompt);
            if (modelProblem) {
                report(job, `could not set the thinking level to High (${modelProblem}) - image and prompt are in, set it and send by hand`, true);
                return;
            }
            step = 'sending';
            const button = await waitFor(() => sendButton(inputArea()), 60000, 'An enabled send button');
            click(button);
            report(job, `${job.label} sent, thinking High - waiting for the image`);
            step = 'waiting for the answer';
            await downloadAnswer(job);
        } catch (e) {
            report(job, `stopped at ${step}: ${e.message}`, true);
        } finally {
            working = false;
        }
    }

    async function fetchAnswer(job) {
        working = true;
        try {
            await downloadAnswer(job);
        } catch (e) {
            report(job, `could not download the image: ${e.message}`, true);
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
        if (job.fetch) {
            // Only the image of the answer in this tab, no new chat
            fetchAnswer(job);
            return;
        }
        // Always a new chat: keep the sheet over the reload and go on there
        sessionStorage.setItem(STORE_KEY, JSON.stringify(job));
        working = true;
        report(job, `${job.label} taken - opening a new chat`);
        location.assign(newChatPath());
    }

    setInterval(poll, POLL_MS);
    poll();
})();
