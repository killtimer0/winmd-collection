#requires -Version 7.2
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/../scripts/toolchain.ps1"
$root = Join-Path $PSScriptRoot "../verification/toolchain-$([guid]::NewGuid())"
New-Item $root -ItemType Directory -Force | Out-Null
foreach ($version in @('10.0.9', '10.0.10', '10.0.11')) {
    New-Item "$root/$version/include" -ItemType Directory -Force | Out-Null
    if ($version -ne '10.0.11') { Set-Content "$root/$version/include/probe.h" '' }
}
$found = Find-CrtVersionedInclude $root 'include' 'probe.h'
if ($found -ne (Resolve-Path "$root/10.0.10/include").ProviderPath) { throw 'Version discovery must choose newest complete input, using numeric version order.' }
$rejected = $false
try { Resolve-CrtInclude $root @('missing.h') 'SdkIncludePath' | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw 'Missing required headers were accepted.' }
New-Item "$root/路径 with spaces" -ItemType Directory | Out-Null
Set-Content "$root/路径 with spaces/probe.h" ''
$resolved = Resolve-CrtInclude "$root/路径 with spaces" @('probe.h') 'SdkIncludePath'
if ($resolved -ne (Resolve-Path "$root/路径 with spaces").ProviderPath) { throw 'Unicode/spaced include path was not preserved.' }
$kits = Join-Path $root 'Kits 路径'
$version = '10.0.26100.0'
foreach ($arch in @('x86', 'x64', 'arm64')) {
    New-Item "$kits/Lib/$version/ucrt/$arch" -ItemType Directory -Force | Out-Null
    Set-Content "$kits/Lib/$version/ucrt/$arch/ucrt.lib" ''
}
$libraries = Get-CrtSdkLib (Join-Path $kits "Include/$version") $null
foreach ($arch in @('x86', 'x64', 'arm64')) {
    if ($libraries[$arch] -ne (Resolve-Path "$kits/Lib/$version/ucrt/$arch/ucrt.lib").ProviderPath) { throw "Import library discovery failed for $arch." }
}
Remove-Item "$kits/Lib/$version/ucrt/x86/ucrt.lib"
$rejected = $false
try { Get-CrtSdkLib (Join-Path $kits "Include/$version") $null | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw 'Missing per-architecture import library was accepted.' }
$rejected = $false
try { Get-CrtSdkLib (Join-Path $kits "Include/$version") (Join-Path $kits 'missing') | Out-Null } catch { $rejected = $true }
if (-not $rejected) { throw 'Missing import library directory was accepted.' }
Push-Location $root
try {
    New-Item out -ItemType Directory | Out-Null
    $rejected = $false
    try { Invoke-CrtStep 'expected-failure' (Resolve-CrtExecutable 'pwsh') @('-NoProfile', '-Command', 'exit 9') } catch { $rejected = $true }
    if (-not $rejected) { throw 'Child process failure was not propagated.' }
}
finally { Pop-Location }
Write-Host 'PASS: numeric discovery, incomplete version filtering, header validation, import library discovery, Unicode paths, child failure propagation'
