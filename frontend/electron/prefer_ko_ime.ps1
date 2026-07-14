# Electron 창 포커스 시 한국어 키보드(IME) + 한글 입력 모드로 전환
$ErrorActionPreference = "SilentlyContinue"

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class PreferKoIme {
  [DllImport("user32.dll", CharSet = CharSet.Unicode)]
  public static extern IntPtr LoadKeyboardLayout(string pwszKLID, uint Flags);
  [DllImport("user32.dll")]
  public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();
  [DllImport("imm32.dll")]
  public static extern IntPtr ImmGetContext(IntPtr hWnd);
  [DllImport("imm32.dll")]
  public static extern bool ImmReleaseContext(IntPtr hWnd, IntPtr hIMC);
  [DllImport("imm32.dll")]
  public static extern bool ImmSetOpenStatus(IntPtr hIMC, bool fOpen);
  [DllImport("imm32.dll")]
  public static extern bool ImmGetConversionStatus(IntPtr hIMC, out uint lpfdwConversion, out uint lpfdwSentence);
  [DllImport("imm32.dll")]
  public static extern bool ImmSetConversionStatus(IntPtr hIMC, uint fdwConversion, uint fdwSentence);

  public const uint KLF_ACTIVATE = 0x00000001;
  public const uint WM_INPUTLANGCHANGEREQUEST = 0x0050;
  public const uint IME_CMODE_NATIVE = 0x0001;
  public const uint IME_CMODE_FULLSHAPE = 0x0008;
}
"@

$hkl = [PreferKoIme]::LoadKeyboardLayout("00000412", [PreferKoIme]::KLF_ACTIVATE)
if ($hkl -eq [IntPtr]::Zero) { exit 0 }

$hwnd = [PreferKoIme]::GetForegroundWindow()
if ($hwnd -ne [IntPtr]::Zero) {
  [void][PreferKoIme]::PostMessage($hwnd, [PreferKoIme]::WM_INPUTLANGCHANGEREQUEST, [IntPtr]::Zero, $hkl)
}

Start-Sleep -Milliseconds 80

$hwnd = [PreferKoIme]::GetForegroundWindow()
if ($hwnd -eq [IntPtr]::Zero) { exit 0 }

$himc = [PreferKoIme]::ImmGetContext($hwnd)
if ($himc -eq [IntPtr]::Zero) { exit 0 }

try {
  [void][PreferKoIme]::ImmSetOpenStatus($himc, $true)
  $conv = [uint32]0
  $sent = [uint32]0
  if ([PreferKoIme]::ImmGetConversionStatus($himc, [ref]$conv, [ref]$sent)) {
    $conv = $conv -bor [PreferKoIme]::IME_CMODE_NATIVE
    $conv = $conv -band (-bnot [PreferKoIme]::IME_CMODE_FULLSHAPE)
    [void][PreferKoIme]::ImmSetConversionStatus($himc, $conv, $sent)
  }
} finally {
  [void][PreferKoIme]::ImmReleaseContext($hwnd, $himc)
}
