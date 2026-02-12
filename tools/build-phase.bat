@echo off
REM Docker Build Matrix - Windows Batch Wrapper
REM Phase別のビルドを実行するバッチファイル

setlocal enabledelayedexpansion

if "%1"=="" goto :show_help
if "%1"=="help" goto :show_help
if "%1"=="--help" goto :show_help
if "%1"=="-h" goto :show_help

set PHASE=%1

if "%PHASE%"=="minimal" (
    echo [Phase: Minimal] 最小構成ビルド
    powershell -Command ".\build-matrix.ps1 -Minimal"
    goto :end
)

if "%PHASE%"=="phase1" (
    echo [Phase 1] CUDA 12.8.1 + Python 3.13 基本構成
    powershell -Command ".\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target runtime"
    if errorlevel 1 goto :error
    powershell -Command ".\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target ray-runtime"
    if errorlevel 1 goto :error
    goto :end
)

if "%PHASE%"=="phase2" (
    echo [Phase 2] CUDA 12.8.1 + Python 3.13 開発環境
    powershell -Command ".\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target devel"
    if errorlevel 1 goto :error
    powershell -Command ".\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target ray-devel"
    if errorlevel 1 goto :error
    powershell -Command ".\build-matrix.ps1 -Cuda 12.8.1 -Python 3.13 -Target marimo-devel"
    if errorlevel 1 goto :error
    goto :end
)

if "%PHASE%"=="phase3" (
    echo [Phase 3] CUDA 13.1.1 + Python 3.14 次世代環境
    powershell -Command ".\build-matrix.ps1 -Cuda 13.1.1 -Python 3.14"
    if errorlevel 1 goto :error
    goto :end
)

if "%PHASE%"=="phase4" (
    echo [Phase 4] CUDA 12.8.1 + Python 3.14 バリエーション
    powershell -Command ".\build-matrix.ps1 -Cuda 12.8.1 -Python 3.14"
    if errorlevel 1 goto :error
    goto :end
)

if "%PHASE%"=="all" (
    echo [All] 全パターンビルド
    powershell -Command ".\build-matrix.ps1 -All"
    goto :end
)

echo エラー: 不明なフェーズ '%PHASE%'
goto :show_help

:show_help
echo Docker Build Matrix - Phase別ビルド実行
echo.
echo 使用方法:
echo   build-phase.bat [phase]
echo.
echo フェーズ:
echo   minimal    最小構成（テスト用）
echo   phase1     Phase 1: CUDA 12.8.1 + Python 3.13 基本構成
echo   phase2     Phase 2: CUDA 12.8.1 + Python 3.13 開発環境
echo   phase3     Phase 3: CUDA 13.1.1 + Python 3.14 次世代環境
echo   phase4     Phase 4: CUDA 12.8.1 + Python 3.14 バリエーション
echo   all        全パターンビルド
echo   help       このヘルプを表示
echo.
echo 例:
echo   build-phase.bat minimal
echo   build-phase.bat phase1
echo   build-phase.bat all
goto :end

:error
echo.
echo ========================================
echo ビルドが失敗しました
echo ========================================
exit /b 1

:end
endlocal
