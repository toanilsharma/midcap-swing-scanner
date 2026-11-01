/**
 * Midcap Swing Terminal - Progressive Web App (PWA) Handler
 * Manages Service Worker lifecycle, Android Install Prompt, and Standalone mode.
 */

(function () {
  'use strict';

  // 1. Standalone Check (already installed and opened from Home Screen)
  const isStandalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true ||
    document.referrer.includes('android-app://');

  if (isStandalone) {
    document.documentElement.classList.add('pwa-standalone');
    console.log('[PWA] Running in standalone native app mode');
    return; // Don't show any install prompts if already running as an installed app
  }

  // 2. Service Worker Registration
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('./sw.js')
        .then((reg) => {
          console.log('[PWA] Service Worker active, scope:', reg.scope);
          reg.addEventListener('updatefound', () => {
            const newWorker = reg.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  console.log('[PWA] New version cached.');
                }
              });
            }
          });
        })
        .catch((err) => {
          console.warn('[PWA] Service Worker registration failed:', err);
        });
    });
  }

  // 3. Android PWA Install Flow
  let deferredPrompt = null;

  function initPwaInstall() {
    const installBtn = document.getElementById('pwaInstallBtn');
    const installBanner = document.getElementById('pwaInstallBanner');
    const bannerInstallBtn = document.getElementById('pwaBannerInstallBtn');
    const bannerDismissBtn = document.getElementById('pwaBannerDismissBtn');

    // Show button on login / header immediately on mobile browsers
    if (installBtn) {
      installBtn.style.display = installBtn.classList.contains('btn-block') ? 'block' : 'inline-flex';
      installBtn.addEventListener('click', handleInstallClick);
    }

    // Check if dismissed recently (24 hours)
    const dismissedTime = localStorage.getItem('pwa_prompt_dismissed');
    const isDismissedRecently =
      dismissedTime && Date.now() - parseInt(dismissedTime, 10) < 24 * 60 * 60 * 1000;

    // Show bottom banner after 1.5s delay if on mobile and not recently dismissed
    const isMobileDevice = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
      navigator.userAgent
    );

    if (installBanner && !isDismissedRecently && isMobileDevice) {
      setTimeout(() => {
        installBanner.style.display = 'block';
      }, 1500);
    }

    // Capture Chrome / Android beforeinstallprompt event whenever it fires
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      console.log('[PWA] beforeinstallprompt captured and ready');

      if (installBtn) {
        installBtn.style.display = installBtn.classList.contains('btn-block') ? 'block' : 'inline-flex';
      }

      if (installBanner && !isDismissedRecently) {
        installBanner.style.display = 'block';
      }
    });

    if (bannerInstallBtn) {
      bannerInstallBtn.addEventListener('click', handleInstallClick);
    }

    if (bannerDismissBtn && installBanner) {
      bannerDismissBtn.addEventListener('click', () => {
        installBanner.style.display = 'none';
        localStorage.setItem('pwa_prompt_dismissed', Date.now().toString());
      });
    }

    // When app is successfully installed
    window.addEventListener('appinstalled', () => {
      console.log('[PWA] App successfully installed!');
      deferredPrompt = null;
      if (installBanner) installBanner.style.display = 'none';
      if (installBtn) installBtn.style.display = 'none';
    });
  }

  async function handleInstallClick() {
    if (deferredPrompt) {
      try {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        console.log('[PWA] User choice:', outcome);
        if (outcome === 'accepted') {
          const banner = document.getElementById('pwaInstallBanner');
          if (banner) banner.style.display = 'none';
          const btn = document.getElementById('pwaInstallBtn');
          if (btn) btn.style.display = 'none';
        }
        deferredPrompt = null;
      } catch (err) {
        console.warn('[PWA] Install prompt error:', err);
        showInstallInstructionsModal();
      }
    } else {
      // Show instant visual 2-step tutorial modal
      showInstallInstructionsModal();
    }
  }

  function showInstallInstructionsModal() {
    const existingModal = document.getElementById('pwaInstructionsModal');
    if (existingModal) {
      existingModal.remove();
    }

    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;

    const modal = document.createElement('div');
    modal.id = 'pwaInstructionsModal';
    modal.className = 'pwa-modal-overlay';
    modal.innerHTML = `
      <div class="pwa-modal-content">
        <div class="pwa-modal-header">
          <div style="display:flex; align-items:center; gap: 10px;">
            <span style="font-size: 24px;">📈</span>
            <h3 style="margin:0; font-size: 18px; color: var(--color-text-light, #fff);">Install on Your Phone</h3>
          </div>
          <button class="pwa-modal-close" id="pwaModalCloseBtn">&times;</button>
        </div>
        <div class="pwa-modal-body">
          <p style="color: var(--color-text-muted, #9e9e9e); font-size: 14px; margin-top: 4px; margin-bottom: 16px;">
            Install <strong>Midcap Swing Terminal</strong> on your Android mobile so you can open it with 1 tap from your home screen without opening Chrome or typing the URL:
          </p>

          ${
            isIOS
              ? `
            <div class="pwa-step-card">
              <div class="pwa-step-num">1</div>
              <div class="pwa-step-text">Tap the <strong>Share</strong> button (square with arrow up) at the bottom of Safari.</div>
            </div>
            <div class="pwa-step-card">
              <div class="pwa-step-num">2</div>
              <div class="pwa-step-text">Scroll down and tap <strong>"Add to Home Screen"</strong>.</div>
            </div>
            `
              : `
            <div class="pwa-step-card">
              <div class="pwa-step-num">1</div>
              <div class="pwa-step-text">In <strong>Chrome</strong> on your phone, tap the <strong>three dots menu (⋮)</strong> in the top-right corner.</div>
            </div>
            <div class="pwa-step-card">
              <div class="pwa-step-num">2</div>
              <div class="pwa-step-text">Tap <strong>"Install app"</strong> or <strong>"Add to Home screen"</strong>.</div>
            </div>
            <div class="pwa-step-card">
              <div class="pwa-step-num">3</div>
              <div class="pwa-step-text">Tap <strong>Install</strong>. The Midcap Swing app icon is immediately added to your home screen!</div>
            </div>
            `
          }
        </div>
        <div class="pwa-modal-footer">
          <button id="pwaModalGotItBtn" class="btn btn-primary btn-block">Understood</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const close = () => modal.remove();
    document.getElementById('pwaModalCloseBtn').addEventListener('click', close);
    document.getElementById('pwaModalGotItBtn').addEventListener('click', close);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) close();
    });
  }

  // Auto-init when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPwaInstall);
  } else {
    initPwaInstall();
  }
})();
