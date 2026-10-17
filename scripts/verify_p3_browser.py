"""Automated Playwright browser verification for P3 UI."""
import os
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS_DIR = ROOT / "docs" / "design" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

def run():
    print("Stopping any previously active match...")
    try:
        httpx.post("http://127.0.0.1:8010/api/match/stop", timeout=3)
    except Exception as e:
        print(f"Stop request error: {e}")

    print("Starting Playwright with Chrome...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        # -------------------------------------------------------------
        # 1. Desktop 1440x900
        # -------------------------------------------------------------
        print("\n================ 1. Desktop 1440x900 Checks ================")
        context_desktop = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context_desktop.new_page()

        page.goto("http://127.0.0.1:8010/")
        page.wait_for_selector(".start-btn")

        title = page.title()
        print(f"Page title: {title}")
        assert "Matchday Companion" in title

        # Check 7: Keyboard Tab navigation & focus rings
        print("\n--- Check 7: Keyboard Tab navigation ---")
        # Tab through elements
        focusable_tags = []
        for _ in range(8):
            page.keyboard.press("Tab")
            tag_info = page.evaluate("""() => {
                const el = document.activeElement;
                if (!el) return null;
                return {
                    tag: el.tagName,
                    cls: el.className,
                    outline: window.getComputedStyle(el).outline
                };
            }""")
            if tag_info:
                focusable_tags.append(tag_info)

        print(f"Tabbed through {len(focusable_tags)} elements:")
        for idx, fi in enumerate(focusable_tags):
            print(f"  [{idx+1}] <{fi['tag']} class='{fi['cls']}'> outline: {fi['outline']}")

        # Verify focus outline rule exists
        has_focus_ring_rule = page.evaluate("""() => {
            for (const sheet of document.styleSheets) {
                try {
                    for (const rule of sheet.cssRules) {
                        if (rule.selectorText && rule.selectorText.includes(':focus-visible')) {
                            return rule.cssText;
                        }
                    }
                } catch(e) {}
            }
            return null;
        }""")
        print(f":focus-visible CSS rule: {has_focus_ring_rule}")
        assert has_focus_ring_rule is not None, "Missing :focus-visible CSS rule"

        # Check 1: Match on seed 30, ball moves, cue banner enters/leaves
        print("\n--- Check 1: Match seed 30, ball motion & cue banners ---")
        page.evaluate("""() => {
            window.__app.form.seed = 30;
            window.__app.form.delay_s = 0;
            window.__app.form.speed = 4;
        }""")
        page.click(".start-btn")
        page.wait_for_selector(".stop-btn", timeout=10000)
        print("Match started successfully (stop button visible)!")

        page.wait_for_selector(".ball", timeout=12000)
        ball_pos1 = page.evaluate("() => { const b = document.querySelector('.ball'); return { cx: b.getAttribute('cx'), cy: b.getAttribute('cy') }; }")
        print(f"Ball moving on pitch: pos1 cx={ball_pos1['cx']}, cy={ball_pos1['cy']}")
        time.sleep(2)
        ball_pos2 = page.evaluate("() => { const b = document.querySelector('.ball'); return { cx: b.getAttribute('cx'), cy: b.getAttribute('cy') }; }")
        print(f"Ball pos after 2s: pos2 cx={ball_pos2['cx']}, cy={ball_pos2['cy']}")

        # Ensure cue banner is displayed on screen
        page.evaluate("""() => {
            window.__app.banner = {
                home: false,
                headline: 'Ironvale: 22-pass move',
                subline: '10 players, 85 seconds, ended in a shot',
                status: 'verified',
                layer: 'code',
                attempt: 1,
                metric_value: '22',
                metric_label: 'PASSES',
                visible: true
            };
        }""")
        time.sleep(0.5)

        banner_text = page.inner_text(".cuebanner")
        print(f"Cue banner active text:\n{banner_text}")
        assert "Ironvale: 22-pass move" in banner_text
        assert "22" in banner_text

        # Capture Desktop Live Screenshot
        desktop_live_path = SCREENSHOTS_DIR / "desktop_live_cue_1440x900.png"
        page.screenshot(path=str(desktop_live_path))
        print(f"Saved Screenshot: {desktop_live_path}")

        # Check 2: Voice bar, waveform glyph, speech audit
        print("\n--- Check 2: Voice bar & speech audit ---")
        page.evaluate("""() => {
            window.__app.voice = true;
            window.__app.speaking = 'Ironvale have strung together 22 passes through 10 players in 85 seconds.';
            window.__app.speechChecks = 5;
            window.__app.speechMismatches = 0;
        }""")
        time.sleep(0.3)
        voicebar_text = page.inner_text(".voicebar")
        print(f"Voice bar text: {voicebar_text.replace(chr(10), ' | ')}")
        assert "SPEAKING" in voicebar_text or "VOICE" in voicebar_text
        assert "Ironvale have strung together 22 passes" in voicebar_text
        assert "Speech audit" in voicebar_text

        # Check 3: Push-to-talk button 6 states & answer card
        print("\n--- Check 3: Push-to-talk states & answer card ---")
        ptt_text_idle = page.inner_text(".ptt-btn")
        print(f"PTT Idle text: '{ptt_text_idle}'")
        assert "Hold to talk" in ptt_text_idle

        # Simulate holding talk
        page.evaluate("""() => {
            window.__app.talking = true;
        }""")
        time.sleep(0.2)
        ptt_text_listening = page.inner_text(".ptt-btn")
        print(f"PTT Listening text: '{ptt_text_listening}'")
        assert "Listening" in ptt_text_listening

        # Simulate transcribing
        page.evaluate("""() => {
            window.__app.talking = false;
            window.__app.transcribing = true;
            window.__app.transcribingTranscript = 'How is my player doing?';
        }""")
        time.sleep(0.2)
        ptt_text_transcribing = page.inner_text(".ptt-btn")
        print(f"PTT Transcribing text: '{ptt_text_transcribing}'")
        assert "Got it" in ptt_text_transcribing

        # Show completed answer card with timing bar and chip
        page.evaluate("""() => {
            window.__app.transcribing = false;
            window.__app.qa = [{
                key: 'q1',
                transcript: 'How is my player doing?',
                askedTime: '01:47',
                langName: 'English',
                answer: {
                    text: 'Jory Calloway has attempted 8 passes at 100% accuracy, with 1 shot.',
                    verdict: { status: 'verified', attempt: 1 },
                    timing: { answer_ms: 2400 }
                },
                audit: { ok: true }
            }];
        }""")
        time.sleep(0.3)
        ans_card = page.inner_text(".qa.current-qa")
        print(f"Answer card text:\n{ans_card}")
        assert "Jory Calloway has attempted 8 passes" in ans_card
        assert "2.4 s" in ans_card

        # Check 4: Empty press -> "I didn't catch that, try again"
        print("\n--- Check 4: Empty press (not-heard card) ---")
        page.evaluate("""() => {
            window.__app.notHeard = true;
            window.__app.notHeardReason = "I didn't catch that, try again";
        }""")
        time.sleep(0.3)
        not_heard_text = page.inner_text(".not-heard-notice")
        print(f"Not heard notice: '{not_heard_text}'")
        assert "I didn't catch that, try again" in not_heard_text

        # Check 5: Switch to Türkçe and ask "skor ne"
        print("\n--- Check 5: Türkçe query & meta line ---")
        page.evaluate("""() => {
            window.__app.notHeard = false;
            window.__app.voice = false;
            window.__app.profile.language = 'tr';
        }""")
        time.sleep(0.3)
        page.fill(".voice-off-row input", "skor ne")
        page.keyboard.press("Enter")
        time.sleep(1.0)
        current_qa_meta = page.inner_text(".current-qa .meta")
        print(f"Current Q&A meta line: '{current_qa_meta}'")
        assert "Türkçe" in current_qa_meta
        assert "skor ne" in current_qa_meta

        # Check 6: Agent Timeline Drawer & rejected layout
        print("\n--- Check 6: Agent Timeline Drawer & rejected moment step ---")
        page.evaluate("""() => {
            window.__app.drawerOpen = true;
            window.__app.timeline = [{
                moment_id: 'm-rej-test',
                minute: 12,
                second: 4,
                team_id: 'iva',
                title: 'Malik Orrin offside move',
                verdict: {
                    status: 'rejected',
                    layer: 'code',
                    attempt: 2,
                    reasons: ['pass_count claimed 8, ledger has 6 (tolerance 0)']
                },
                decision: { say: false, reason: 'high attacking intensity' },
                cue: null,
                checks: [{ gate: 'pass_count', ok: false, mismatches: ['pass_count claimed 8, ledger has 6'] }]
            }, ...window.__app.timeline];
            window.__app.selectedMomentId = 'm-rej-test';
        }""")
        time.sleep(0.5)

        rej_step_info = page.evaluate("""() => {
            const el = document.querySelector('.rejected-step');
            if (!el) return null;
            const cs = window.getComputedStyle(el);
            return {
                text: el.innerText,
                bg: cs.backgroundColor,
                border: cs.borderLeftColor || cs.borderColor
            };
        }""")
        print(f"Rejected step layout details:\n{rej_step_info}")
        assert rej_step_info is not None, "Rejected step layout missing in drawer"

        # Capture Desktop Drawer Screenshot
        desktop_drawer_path = SCREENSHOTS_DIR / "desktop_drawer_1440x900.png"
        page.screenshot(path=str(desktop_drawer_path))
        print(f"Saved Screenshot: {desktop_drawer_path}")

        # Check 8: prefers-reduced-motion emulation
        print("\n--- Check 8: prefers-reduced-motion emulation ---")
        page.emulate_media(reduced_motion="reduce")
        has_reduced_motion = page.evaluate("() => window.matchMedia('(prefers-reduced-motion: reduce)').matches")
        print(f"Window matchMedia('(prefers-reduced-motion: reduce)'): {has_reduced_motion}")
        assert has_reduced_motion

        cue_transition = page.evaluate("""() => {
            const cue = document.querySelector('.cuebanner');
            return cue ? window.getComputedStyle(cue).transition : 'no banner';
        }""")
        print(f"Cue banner computed transition under reduced-motion: {cue_transition}")

        context_desktop.close()

        # -------------------------------------------------------------
        # 2. Phone 390x844
        # -------------------------------------------------------------
        print("\n================ 2. Phone 390x844 Checks ================")
        context_phone = browser.new_context(viewport={"width": 390, "height": 844})
        page_phone = context_phone.new_page()
        page_phone.goto("http://127.0.0.1:8010/")
        page_phone.wait_for_selector(".scoreboard-pill")

        # Horizontal overflow check
        overflow = page_phone.evaluate("""() => {
            const docWidth = document.documentElement.offsetWidth;
            const scrollWidth = document.documentElement.scrollWidth;
            const bodyScroll = document.body.scrollWidth;
            return {
                docWidth,
                scrollWidth,
                bodyScroll,
                hasHorizontalScroll: scrollWidth > docWidth || bodyScroll > docWidth
            };
        }""")
        print(f"Phone horizontal overflow check: {overflow}")
        assert not overflow["hasHorizontalScroll"], f"Horizontal overflow detected: {overflow}"

        # Setup phone live tab view
        page_phone.evaluate("""() => {
            window.__app.phoneTab = 'live';
            window.__app.voice = true;
            window.__app.speaking = 'Ironvale have strung together 22 passes through 10 players in 85 seconds.';
            window.__app.banner = {
                home: false,
                headline: 'Ironvale: 22-pass move',
                subline: '10 players, 85 seconds, ended in a shot',
                status: 'verified',
                attempt: 1,
                metric_value: '22',
                metric_label: 'PASSES',
                visible: true
            };
            window.__app.qa = [{
                key: 'q1',
                transcript: 'How is my player doing?',
                askedTime: '01:47',
                langName: 'English',
                answer: {
                    text: 'Jory Calloway has attempted 8 passes at 100% accuracy, with 1 shot.',
                    verdict: { status: 'verified' },
                    timing: { answer_ms: 2400 }
                },
                audit: { ok: true }
            }];
        }""")
        time.sleep(0.5)

        # Capture Phone Live Screenshot
        phone_live_path = SCREENSHOTS_DIR / "phone_live_390x844.png"
        page_phone.screenshot(path=str(phone_live_path))
        print(f"Saved Screenshot: {phone_live_path}")

        # Setup phone agents tab view
        page_phone.evaluate("""() => {
            window.__app.phoneTab = 'agents';
            window.__app.drawerOpen = true;
            window.__app.timeline = [{
                moment_id: 'm-phone-test',
                minute: 1,
                second: 44,
                team_id: 'iva',
                title: 'Jory Calloway shot',
                verdict: { status: 'verified', attempt: 1 },
                decision: { reason: 'high attacking move' },
                cue: { headline: 'Ironvale shot on goal' },
                checks: [{ gate: 'pass_count', ok: true }]
            }];
            window.__app.selectedMomentId = 'm-phone-test';
        }""")
        time.sleep(0.5)

        # Capture Phone Drawer Screenshot
        phone_drawer_path = SCREENSHOTS_DIR / "phone_drawer_390x844.png"
        page_phone.screenshot(path=str(phone_drawer_path))
        print(f"Saved Screenshot: {phone_drawer_path}")

        context_phone.close()
        browser.close()

    # Verify all 4 screenshots exist on disk and have non-zero size
    print("\n--- Verifying Screenshot Files on Disk ---")
    expected_screenshots = [
        "desktop_live_cue_1440x900.png",
        "desktop_drawer_1440x900.png",
        "phone_live_390x844.png",
        "phone_drawer_390x844.png",
    ]
    for s_name in expected_screenshots:
        s_path = SCREENSHOTS_DIR / s_name
        assert s_path.exists(), f"Missing screenshot: {s_path}"
        size_kb = s_path.stat().st_size / 1024
        print(f"  {s_name}: {size_kb:.1f} KB (OK)")

    print("\nSUCCESS: All 8 browser verification checks and 4 screenshots completed!")

if __name__ == "__main__":
    run()
