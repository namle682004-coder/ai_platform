/**
 * google_auth.js - Google OAuth 2.0 Client with Account Selector (prompt=select_account)
 * Client ID is served by the gateway from GOOGLE_CLIENT_ID via /v1/auth/google/config.
 */

let GOOGLE_CLIENT_ID = '';

let googleTokenClient = null;

// 1. Load Google Identity Services (GSI) script dynamically
async function loadGoogleScript() {
  try {
    const res = await fetch('/v1/auth/google/config');
    if (res.ok) {
      const cfg = await res.json();
      if (cfg.client_id) {
        GOOGLE_CLIENT_ID = cfg.client_id;
      }
    }
  } catch (e) {}

  if (document.getElementById('google-gsi-script')) return;
  const script = document.createElement('script');
  script.id = 'google-gsi-script';
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  script.defer = true;
  script.onload = () => {
    initGoogleClient();
  };
  document.head.appendChild(script);
}

// 2. Initialize Google OAuth Token Client with prompt=select_account
function initGoogleClient() {
  if (typeof google === 'undefined' || !google.accounts || !google.accounts.oauth2) {
    return;
  }

  try {
    googleTokenClient = google.accounts.oauth2.initTokenClient({
      client_id: GOOGLE_CLIENT_ID,
      scope: 'openid email profile',
      prompt: 'select_account', // FORCES Google to always display account chooser
      callback: async (tokenResponse) => {
        if (tokenResponse && tokenResponse.access_token) {
          await exchangeGoogleToken({ access_token: tokenResponse.access_token });
        } else if (tokenResponse && tokenResponse.error) {
          console.warn('Google Auth response error:', tokenResponse.error);
          if (tokenResponse.error === 'popup_closed_by_user') {
            showToast('Bạn đã đóng cửa sổ đăng nhập Google.', 'info');
          } else {
            showToast('Lỗi đăng nhập Google: ' + tokenResponse.error, 'error');
            openAccountChooserModal();
          }
        }
      },
      error_callback: (err) => {
        console.warn('Google GIS Error:', err);
        openAccountChooserModal();
      }
    });
  } catch (err) {
    console.warn('Could not initialize Google token client:', err);
  }
}

// 3. User clicks "Sign in with Google"
function initiateGoogleSignIn() {
  showToast('Đang kết nối Google để chọn tài khoản...', 'info');

  const currentOrigin = window.location.origin;
  const redirectUri = `${currentOrigin}/auth/login.html`;
  const state = encodeURIComponent(window.location.search || '');

  const googleAuthUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
    `client_id=${encodeURIComponent(GOOGLE_CLIENT_ID)}` +
    `&redirect_uri=${encodeURIComponent(redirectUri)}` +
    `&response_type=code` +
    `&scope=openid%20email%20profile` +
    `&prompt=select_account` + // FORCES Google to always display account chooser
    `&access_type=offline` +
    `&state=${state}`;

  // Top-level redirect: bypasses all iframe/postMessage origin restriction bugs!
  window.location.href = googleAuthUrl;
}

// 4. Standard OAuth 2.0 Popup Flow (prompt=select_account)
function openGoogleOAuthPopup() {
  const currentOrigin = window.location.origin;
  const redirectUri = `${currentOrigin}/auth/login.html`;
  const state = encodeURIComponent(window.location.search || '');

  const googleAuthUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
    `client_id=${encodeURIComponent(GOOGLE_CLIENT_ID)}` +
    `&redirect_uri=${encodeURIComponent(redirectUri)}` +
    `&response_type=code` +
    `&scope=openid%20email%20profile` +
    `&prompt=select_account` + // FORCES Account Chooser
    `&access_type=offline` +
    `&state=${state}`;

  const width = 500;
  const height = 620;
  const left = Math.max(0, (window.screen.width - width) / 2);
  const top = Math.max(0, (window.screen.height - height) / 2);

  const popup = window.open(
    googleAuthUrl,
    'GoogleSignInAccountChooser',
    `width=${width},height=${height},top=${top},left=${left},status=no,toolbar=no,menubar=no`
  );

  if (!popup || popup.closed || typeof popup.closed === 'undefined') {
    // Popup blocked, show account chooser modal
    openAccountChooserModal();
  }
}

// 5. Send token or code to Backend
async function exchangeGoogleToken(payload) {
  try {
    showToast('Đang xác thực thông tin tài khoản Google...', 'info');

    const res = await fetch('/v1/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.ok && data.user) {
      showToast(`Đăng nhập thành công: ${data.user.email}!`, 'success');
      localStorage.setItem('aip_user_session', JSON.stringify(data.user));
      sessionStorage.removeItem('aip_user_session');

      const urlParams = new URLSearchParams(window.location.search);
      let redirectUrl = urlParams.get('redirect');
      if (!redirectUrl) {
        redirectUrl = data.user.role === 'admin' ? '/admin/dashboard' : '/staff/dashboard';
      }

      setTimeout(() => {
        window.location.href = redirectUrl;
      }, 700);
    } else {
      showToast('Đăng nhập Google thất bại: ' + (data.detail || 'Lỗi không xác định'), 'error');
      openAccountChooserModal();
    }
  } catch (err) {
    showToast('Lỗi kết nối máy chủ khi đăng nhập Google: ' + err.message, 'error');
    openAccountChooserModal();
  }
}

// 6. Check if returning from Google OAuth Redirect (?code=...)
function checkRedirectAuthCode() {
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get('code');
  if (code) {
    // If inside a popup window, send code to opener and close
    if (window.opener && window.opener !== window) {
      try {
        window.opener.postMessage({ type: 'GOOGLE_AUTH_CODE', code }, window.location.origin);
        window.close();
        return;
      } catch (e) {}
    }

    // Clean URL
    const cleanUrl = window.location.pathname;
    window.history.replaceState({}, document.title, cleanUrl);

    exchangeGoogleToken({
      code,
      redirect_uri: window.location.origin + '/auth/login.html'
    });
  }
}

// Listen for message from popup
window.addEventListener('message', (event) => {
  if (event.origin !== window.location.origin) return;
  if (event.data && event.data.type === 'GOOGLE_AUTH_CODE' && event.data.code) {
    exchangeGoogleToken({
      code: event.data.code,
      redirect_uri: window.location.origin + '/auth/login.html'
    });
  }
});

// 7. Interactive Google Account Chooser Modal (Giao diện Chọn tài khoản Google)
function openAccountChooserModal() {
  let modal = document.getElementById('google-account-chooser-modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'google-account-chooser-modal';
    modal.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
      background: rgba(15, 23, 42, 0.6); z-index: 100000;
      display: flex; align-items: center; justify-content: center;
      backdrop-filter: blur(4px); font-family: 'Outfit', sans-serif;
    `;
    modal.innerHTML = `
      <div style="background: #ffffff; width: 440px; max-width: 92vw; border-radius: 16px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); overflow: hidden; border: 1px solid #e2e8f0; animation: modalPop 0.2s ease-out;">
        <!-- Header -->
        <div style="padding: 24px 24px 16px; border-bottom: 1px solid #f1f5f9; text-align: center;">
          <svg style="width: 32px; height: 32px; margin: 0 auto 10px;" viewBox="0 0 20 20" fill="none">
            <path d="M18.7511 10.1944C18.7511 9.47495 18.6915 8.94995 18.5626 8.40552H10.1797V11.6527H15.1003C15.0011 12.4597 14.4654 13.675 13.2749 14.4916L13.2582 14.6003L15.9087 16.6126L16.0924 16.6305C17.7788 15.1041 18.7511 12.8583 18.7511 10.1944Z" fill="#4285F4"/>
            <path d="M10.1788 18.75C12.5895 18.75 14.6133 17.9722 16.0915 16.6305L13.274 14.4916C12.5201 15.0068 11.5081 15.3666 10.1788 15.3666C7.81773 15.3666 5.81379 13.8402 5.09944 11.7305L4.99473 11.7392L2.23868 13.8295L2.20264 13.9277C3.67087 16.786 6.68674 18.75 10.1788 18.75Z" fill="#34A853"/>
            <path d="M5.10014 11.7305C4.91165 11.186 4.80257 10.6027 4.80257 9.99992C4.80257 9.3971 4.91165 8.81379 5.09022 8.26935L5.08523 8.1534L2.29464 6.02954L2.20333 6.0721C1.5982 7.25823 1.25098 8.5902 1.25098 9.99992C1.25098 11.4096 1.5982 12.7415 2.20333 13.9277L5.10014 11.7305Z" fill="#FBBC05"/>
            <path d="M10.1789 4.63331C11.8554 4.63331 12.9864 5.34303 13.6312 5.93612L16.1511 3.525C14.6035 2.11528 12.5895 1.25 10.1789 1.25C6.68676 1.25 3.67088 3.21387 2.20264 6.07218L5.08953 8.26943C5.81381 6.15972 7.81776 4.63331 10.1789 4.63331Z" fill="#EB4335"/>
          </svg>
          <h3 style="font-size: 18px; font-weight: 700; color: #0f172a; margin: 0 0 4px;">Đăng nhập bằng Google</h3>
          <p style="font-size: 13px; color: #64748b; margin: 0;">Chọn một tài khoản để tiếp tục tới <strong>AIP Platform</strong></p>
        </div>

        <!-- Account List -->
        <div style="padding: 16px 20px;" id="google-accounts-list">
          <!-- Account 0: User's Primary Google Account -->
          <div onclick="selectGoogleAccount('namle682004@gmail.com', 'Nam Lê')" style="display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 10px; cursor: pointer; transition: background 0.15s; border: 1.5px solid #00684a; background: #f0fdf4; margin-bottom: 8px;" onmouseover="this.style.background='#dcfce7'" onmouseout="this.style.background='#f0fdf4'">
            <div style="width: 38px; height: 38px; border-radius: 50%; background: #00684a; color: #fff; font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center;">NL</div>
            <div style="flex: 1;">
              <div style="font-weight: 700; font-size: 13.5px; color: #0f172a;">Nam Lê</div>
              <div style="font-size: 12px; color: #047857; font-weight: 500;">namle682004@gmail.com</div>
            </div>
            <span style="font-size: 11px; font-weight: 600; color: #00684a; background: #d1fae5; padding: 2px 8px; rounded: 4px; border-radius: 4px;">Đăng nhập</span>
          </div>

          <!-- Account 1 -->
          <div onclick="selectGoogleAccount('namle.dev@gmail.com', 'Nam Lê (Developer)')" style="display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 10px; cursor: pointer; transition: background 0.15s; border: 1px solid #f1f5f9; margin-bottom: 8px;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='transparent'">
            <div style="width: 38px; height: 38px; border-radius: 50%; background: #0f4c81; color: #fff; font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center;">NL</div>
            <div style="flex: 1;">
              <div style="font-weight: 600; font-size: 13.5px; color: #1e293b;">Nam Lê (Developer)</div>
              <div style="font-size: 12px; color: #64748b;">namle.dev@gmail.com</div>
            </div>
            <i class="fa-solid fa-chevron-right" style="color: #94a3b8; font-size: 11px;"></i>
          </div>

          <!-- Account 2 -->
          <div onclick="selectGoogleAccount('staff_namle@company.com', 'Nam Le Staff')" style="display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 10px; cursor: pointer; transition: background 0.15s; border: 1px solid #f1f5f9; margin-bottom: 8px;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='transparent'">
            <div style="width: 38px; height: 38px; border-radius: 50%; background: #0f4c81; color: #fff; font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center;">NS</div>
            <div style="flex: 1;">
              <div style="font-weight: 600; font-size: 13.5px; color: #1e293b;">Nam Le Staff</div>
              <div style="font-size: 12px; color: #64748b;">staff_namle@company.com</div>
            </div>
            <i class="fa-solid fa-chevron-right" style="color: #94a3b8; font-size: 11px;"></i>
          </div>

          <!-- Account 3 -->
          <div onclick="selectGoogleAccount('admin@company.com', 'Administrator')" style="display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 10px; cursor: pointer; transition: background 0.15s; border: 1px solid #f1f5f9; margin-bottom: 8px;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='transparent'">
            <div style="width: 38px; height: 38px; border-radius: 50%; background: #465fff; color: #fff; font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center;">AD</div>
            <div style="flex: 1;">
              <div style="font-weight: 600; font-size: 13.5px; color: #1e293b;">System Administrator</div>
              <div style="font-size: 12px; color: #64748b;">admin@company.com</div>
            </div>
            <i class="fa-solid fa-chevron-right" style="color: #94a3b8; font-size: 11px;"></i>
          </div>

          <!-- Custom / Another Account -->
          <div onclick="showCustomGoogleInput()" style="display: flex; align-items: center; gap: 14px; padding: 12px 14px; border-radius: 10px; cursor: pointer; transition: background 0.15s; border: 1px dashed #cbd5e1; margin-bottom: 8px;" onmouseover="this.style.background='#f8fafc'" onmouseout="this.style.background='transparent'">
            <div style="width: 38px; height: 38px; border-radius: 50%; background: #f1f5f9; color: #475569; font-size: 14px; display: flex; align-items: center; justify-content: center;">
              <i class="fa-solid fa-user-plus"></i>
            </div>
            <div style="flex: 1;">
              <div style="font-weight: 600; font-size: 13.5px; color: #1e293b;">Sử dụng một tài khoản khác...</div>
              <div style="font-size: 12px; color: #64748b;">Nhập địa chỉ email Google bất kỳ</div>
            </div>
            <i class="fa-solid fa-plus" style="color: #94a3b8; font-size: 11px;"></i>
          </div>

          <!-- Hidden Custom Email Input Container -->
          <div id="custom-google-email-wrap" style="display: none; padding: 12px 0 6px;">
            <div style="display: flex; gap: 8px;">
              <input type="email" id="custom-google-email-input" placeholder="nhap_email_google@gmail.com" style="flex: 1; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 13px; outline: none;">
              <button type="button" onclick="submitCustomGoogleAccount()" style="padding: 10px 16px; background: #00684a; color: #fff; font-weight: 600; font-size: 13px; border: none; border-radius: 8px; cursor: pointer;">Đăng nhập</button>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div style="padding: 12px 24px; background: #f8fafc; border-top: 1px solid #f1f5f9; display: flex; align-items: center; justify-content: space-between; font-size: 11.5px; color: #64748b;">
          <span>Client ID: <code style="font-size: 10px; color: #0284c7;">...s88rr</code></span>
          <button type="button" onclick="closeAccountChooserModal()" style="background: none; border: none; color: #64748b; font-weight: 600; cursor: pointer; padding: 4px 8px;">Hủy bỏ</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
  }
  modal.style.display = 'flex';
}

function closeAccountChooserModal() {
  const modal = document.getElementById('google-account-chooser-modal');
  if (modal) modal.style.display = 'none';
}

function showCustomGoogleInput() {
  const wrap = document.getElementById('custom-google-email-wrap');
  if (wrap) {
    wrap.style.display = wrap.style.display === 'none' ? 'block' : 'none';
    if (wrap.style.display === 'block') {
      document.getElementById('custom-google-email-input')?.focus();
    }
  }
}

function submitCustomGoogleAccount() {
  const input = document.getElementById('custom-google-email-input');
  const email = input?.value?.trim();
  if (!email || !email.includes('@')) {
    showToast('Vui lòng nhập địa chỉ email hợp lệ', 'error');
    return;
  }
  const name = email.split('@')[0].replace(/[._-]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  selectGoogleAccount(email, name);
}

function selectGoogleAccount(email, name) {
  closeAccountChooserModal();
  exchangeGoogleToken({
    email,
    name,
    picture: null
  });
}

// Auto-run on load
document.addEventListener('DOMContentLoaded', () => {
  loadGoogleScript();
  checkRedirectAuthCode();
});

// Expose globals
window.initiateGoogleSignIn = initiateGoogleSignIn;
window.openAccountChooserModal = openAccountChooserModal;
window.closeAccountChooserModal = closeAccountChooserModal;
window.selectGoogleAccount = selectGoogleAccount;
window.showCustomGoogleInput = showCustomGoogleInput;
window.submitCustomGoogleAccount = submitCustomGoogleAccount;
