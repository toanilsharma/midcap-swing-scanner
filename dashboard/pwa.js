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
  }

  // 2. Service Worker Registration
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('./sw.js')
        .then((reg) => {
          console.log('[PWA] Service Worker active, scope:', reg.scope);
          // Check for worker updates
          reg.addEventListener('updatefound', () => {
            const newWorker = reg.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', () => {
                if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                  console.log('[PWA] New version available.');
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
    if (isStandalone) return;

    const installHeaderBtn = document.getElementById('pwaInstallBtn');
    const installBanner = document.getElementById('pwaInstallBanner');
    const bannerInstallBtn = document.getElementById('pwaBannerInstallBtn');
    const bannerDismissBtn = document.getElementById('pwaBannerDismissBtn');

    // Always expose header install button on mobile/desktop browsers
    if (installHeaderBtn) {
      installHeaderBtn.style.display = 'inline-flex';
      installHeaderBtn.addEventListener('click', handleInstallClick);
    }

    // Check if dismissed recently (24 hours)
    const dismissedTime = localStorage.getItem('pwa_prompt_dismissed');
    const isDismissedRecently =
      dismissedTime && Date.now() - parseInt(dismissedTime, 10) < 24 * 60 * 60 * 1000;

    // Listen for Chrome / Android beforeinstallprompt
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      deferredPrompt = e;
      console.log('[PWA] beforeinstallprompt captured');

      if (installHeaderBtn) {
        installHeaderBtn.style.display = 'inline-flex';
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

    // Check when app is installed
    window.addEventListener('appinstalled', () => {
      console.log('[PWA] App successfully installed!');
      deferredPrompt = null;
      if (installBanner) installBanner.style.display = 'none';
      if (installHeaderBtn) installHeaderBtn.style.display = 'none';
    });
  }

  async function handleInstallClick() {
    if (deferredPrompt) {
      // Chrome Android native prompt
      try {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        console.log('[PWA] User response to install prompt:', outcome);
        if (outcome === 'accepted') {
          const banner = document.getElementById('pwaInstallBanner');
          if (banner) banner.style.display = 'none';
          const btn = document.getElementById('pwaInstallBtn');
          if (btn) btn.style.display = 'none';
        }
        deferredPrompt = null;
      } catch (err) {
        console.warn('[PWA] Install prompt error:', err);
      }
    } else {
      // Fallback instructions modal for Android/iOS users
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
            <h3 style="margin:0; font-size: 18px; color: var(--color-text-light, #fff);">Install Midcap Swing App</h3>
          </div>
          <button class="pwa-modal-close" id="pwaModalCloseBtn">&times;</button>
        </div>
        <div class="pwa-modal-body">
          <p style="color: var(--color-text-muted, #9e9e9e); font-size: 14px; margin-top: 4px; margin-bottom: 16px;">
            Install to launch directly from your home screen in full screen without typing the URL in Chrome.
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
              <div class="pwa-step-text">Tap the <strong>three dots menu (⋮)</strong> at the top right of Chrome.</div>
            </div>
            <div class="pwa-step-card">
              <div class="pwa-step-num">2</div>
              <div class="pwa-step-text">Select <strong>"Install app"</strong> or <strong>"Add to Home screen"</strong>.</div>
            </div>
            <div class="pwa-step-card">
              <div class="pwa-step-num">3</div>
              <div class="pwa-step-text">Tap <strong>Install</strong>. The Midcap Swing icon will appear on your phone's home screen!</div>
            </div>
            `
          }
        </div>
        <div class="pwa-modal-footer">
          <button id="pwaModalGotItBtn" class="btn btn-primary btn-block">Got It</button>
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

