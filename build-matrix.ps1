# Docker Build Matrix - PowerShell Wrapper
# uv run python tools/build_matrix.py を簡単に実行するためのラッパー

param(
    [switch]$All,
    [switch]$Minimal,
    [string]$Cuda,
    [string]$Python,
    [string]$Target,
    [switch]$DryRun,
    [switch]$Help
)

function Show-Help {
    Write-Host @"
Docker Build Matrix - PowerShell Wrapper

使用方法:
  .\build-matrix.ps1 [オプション]

オプション:
  -All             全ビルドを実行
  -Minimal         最小構成のテストビルド
  -Cuda <version>  特定のCUDAバージョン (例: 12.8.1)
  -Python <ver>    特定のPythonバージョン (例: 3.13)
  -Target <name>   特定のターゲット (例: marimo-runtime)
  -DryRun          コマンドを表示するのみ
  -Help            このヘルプを表示

例:
  # 最小構成でビルド
  .\build-matrix.ps1 -Minimal

  # 全ビルド実行
  .\build-matrix.ps1 -All

  # CUDA 12.8.1のみビルド
  .\build-matrix.ps1 -Cuda 12.8.1

  # Python 3.13のmarimo-runtimeのみビルド
  .\build-matrix.ps1 -Python 3.13 -Target marimo-runtime

  # ドライラン
  .\build-matrix.ps1 -All -DryRun
"@
}

if ($Help) {
    Show-Help
    exit 0
}

# 引数を構築
$args_list = @()

if ($All) { $args_list += "--all" }
if ($Minimal) { $args_list += "--minimal" }
if ($Cuda) { $args_list += "--cuda"; $args_list += $Cuda }
if ($Python) { $args_list += "--python"; $args_list += $Python }
if ($Target) { $args_list += "--target"; $args_list += $Target }
if ($DryRun) { $args_list += "--dry-run" }

# 引数が指定されていない場合
if ($args_list.Count -eq 0) {
    Write-Host "エラー: オプションを指定してください" -ForegroundColor Red
    Write-Host ""
    Show-Help
    exit 1
}

# Python スクリプトを実行
Write-Host "実行中: uv run python tools/build_matrix.py $($args_list -join ' ')" -ForegroundColor Cyan
& uv run python tools/build_matrix.py @args_list

exit $LASTEXITCODE
