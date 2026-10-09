/**
 * Grabber — Showcase & Documentation Script
 * Features: Dark/Light Mode Switcher, Interactive Terminal Tabs,
 * Clipboard Copying, Memory & Performance Simulator, Mobile Menu.
 * Copyright (c) 2026 Gabriele Vianello.
 */

(function () {
  'use strict';

  // ==========================================================================
  // 1. Theme Management (Dark / Light Mode)
  // ==========================================================================
  const THEME_STORAGE_KEY = 'grabber-theme-preference';
  const themeToggleBtn = document.getElementById('theme-toggle-btn');

  function getPreferredTheme() {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    if (savedTheme) {
      return savedTheme;
    }
    // Fallback to system preference (default dark if preferred or unspecified)
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);

    if (themeToggleBtn) {
      themeToggleBtn.setAttribute(
        'aria-label',
        theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
      );
      themeToggleBtn.setAttribute(
        'title',
        theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
      );
    }
  }

  // Initialize theme immediately
  const initialTheme = getPreferredTheme();
  applyTheme(initialTheme);

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      applyTheme(newTheme);
    });
  }

  // Listen to OS scheme changes if user hasn't explicitly set preference
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (!localStorage.getItem(THEME_STORAGE_KEY)) {
        applyTheme(e.matches ? 'dark' : 'light');
      }
    });
  }

  // ==========================================================================
  // 2. Terminal & Code Snippet Tabs
  // ==========================================================================
  const terminalTabs = document.querySelectorAll('.terminal-tab');
  const terminalPanels = document.querySelectorAll('.terminal-panel');

  terminalTabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      const targetId = tab.getAttribute('data-target');

      // Update active tab button
      terminalTabs.forEach((t) => t.classList.remove('active'));
      tab.classList.add('active');

      // Update active panel
      terminalPanels.forEach((panel) => {
        if (panel.id === targetId) {
          panel.classList.add('active');
        } else {
          panel.classList.remove('active');
        }
      });
    });
  });

  // ==========================================================================
  // 3. Copy to Clipboard Functionality
  // ==========================================================================
  const copyButtons = document.querySelectorAll('.copy-btn, .btn-copy-code');

  copyButtons.forEach((btn) => {
    btn.addEventListener('click', async () => {
      let codeToCopy = '';

      // Check if target is explicitly given by data-code or container
      const targetSelector = btn.getAttribute('data-copy-target');
      if (targetSelector) {
        const targetElem = document.querySelector(targetSelector);
        if (targetElem) {
          codeToCopy = targetElem.innerText.trim();
        }
      } else {
        // Fallback: look for the active terminal panel
        const activePanel = document.querySelector('.terminal-panel.active code, .terminal-panel.active pre');
        if (activePanel) {
          codeToCopy = activePanel.innerText.trim();
        }
      }

      if (!codeToCopy) return;

      try {
        await navigator.clipboard.writeText(codeToCopy);
        const originalText = btn.innerHTML;
        btn.innerHTML = `
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
          <span style="color: #10b981;">Copied!</span>
        `;
        setTimeout(() => {
          btn.innerHTML = originalText;
        }, 2200);
      } catch (err) {
        console.error('Clipboard copy failed:', err);
      }
    });
  });

  // ==========================================================================
  // 4. Interactive Memory & Benchmark Simulator
  // ==========================================================================
  const datasetProfiles = {
    '5GB': {
      sizeText: '5 GB Dataset',
      grabberRam: '112 MB',
      grabberPercent: 8,
      grabberTime: '1.14 s',
      tradRam: '18.4 GB',
      tradPercent: 55,
      tradStatus: 'High RAM Pressure (Paging)',
      tradStatusClass: 'text-warning'
    },
    '15GB': {
      sizeText: '13.5 GB Dataset (Test 1 - 24M Rows)',
      grabberRam: '148 MB',
      grabberPercent: 12,
      grabberTime: '2.81 s',
      tradRam: '52.6 GB',
      tradPercent: 85,
      tradStatus: 'OS Thrashing / Virtual Memory Spike',
      tradStatusClass: 'text-danger'
    },
    '40GB': {
      sizeText: '40 GB Heterogeneous Parquet / CSV',
      grabberRam: '175 MB',
      grabberPercent: 15,
      grabberTime: '6.45 s',
      tradRam: '160+ GB',
      tradPercent: 100,
      tradStatus: 'CRASH: SIGKILL Out-of-Memory (OOM)',
      tradStatusClass: 'text-danger'
    },
    '70GB': {
      sizeText: '62 GB Complex XML (Annihilation Benchmark)',
      grabberRam: '28.1 MB (Constant)',
      grabberPercent: 4,
      grabberTime: '4.49 s (Streaming 288 MB/s)',
      tradRam: '310+ GB',
      tradPercent: 100,
      tradStatus: 'CRASH: Instant Tree Heap Exhaustion',
      tradStatusClass: 'text-danger'
    }
  };

  const sizePillButtons = document.querySelectorAll('.size-pill-btn');
  const simGrabberRam = document.getElementById('sim-grabber-ram');
  const simGrabberTime = document.getElementById('sim-grabber-time');
  const simGrabberBar = document.getElementById('sim-grabber-bar');

  const simTradRam = document.getElementById('sim-trad-ram');
  const simTradStatus = document.getElementById('sim-trad-status');
  const simTradBar = document.getElementById('sim-trad-bar');

  sizePillButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const sizeKey = btn.getAttribute('data-size');
      const profile = datasetProfiles[sizeKey];
      if (!profile) return;

      // Update active button state
      sizePillButtons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      // Animate Grabber metrics
      if (simGrabberRam) simGrabberRam.textContent = profile.grabberRam;
      if (simGrabberTime) simGrabberTime.textContent = profile.grabberTime;
      if (simGrabberBar) simGrabberBar.style.width = `${profile.grabberPercent}%`;

      // Animate Traditional metrics
      if (simTradRam) simTradRam.textContent = profile.tradRam;
      if (simTradStatus) {
        simTradStatus.textContent = profile.tradStatus;
        simTradStatus.style.color = profile.tradPercent >= 80 ? '#ef4444' : '#f59e0b';
      }
      if (simTradBar) simTradBar.style.width = `${profile.tradPercent}%`;
    });
  });

  // ==========================================================================
  // 5. Mobile Navigation Menu Toggle
  // ==========================================================================
  const navToggleBtn = document.getElementById('nav-toggle-btn');
  const navLinks = document.getElementById('nav-links');

  if (navToggleBtn && navLinks) {
    navToggleBtn.addEventListener('click', () => {
      navLinks.classList.toggle('mobile-open');
    });

    // Close mobile menu when clicking outside or on a link
    navLinks.querySelectorAll('a').forEach((link) => {
      link.addEventListener('click', () => {
        navLinks.classList.remove('mobile-open');
      });
    });
  }

  // Smooth scroll offset adjustment for fixed navbar
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener('click', function (e) {
      const targetId = this.getAttribute('href');
      if (targetId === '#') return;
      const targetElement = document.querySelector(targetId);
      if (targetElement) {
        e.preventDefault();
        const headerOffset = 80;
        const elementPosition = targetElement.getBoundingClientRect().top;
        const offsetPosition = elementPosition + window.pageYOffset - headerOffset;

        window.scrollTo({
          top: offsetPosition,
          behavior: 'smooth'
        });
      }
    });
  });

  // ==========================================================================
  // Latest release version badge (static HTML value is only a fallback)
  // ==========================================================================
  const versionBadge = document.getElementById('app-version');
  if (versionBadge && window.fetch) {
    fetch('https://api.github.com/repos/Vinello28/grabber/releases/latest', {
      headers: { Accept: 'application/vnd.github+json' }
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((release) => {
        const tag = release && release.tag_name;
        if (tag) {
          versionBadge.textContent = /^v/i.test(tag) ? tag : 'v' + tag;
        }
      })
      .catch(() => {});
  }

})();
