param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Out
)
# Windows 内置 OCR（Windows.Media.Ocr），零下载、离线、自带中文模型。
# 输出 JSON 到文件（避免 PowerShell 控制台编码把中文弄坏）。
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime

function Get-AsTaskGeneric {
    foreach ($m in [System.WindowsRuntimeSystemExtensions].GetMethods()) {
        if ($m.Name -eq 'AsTask' -and $m.IsGenericMethodDefinition) {
            $ps = $m.GetParameters()
            if ($ps.Count -eq 1 -and $ps[0].ParameterType.Name -like 'IAsyncOperation*') { return $m }
        }
    }
    throw 'AsTask generic method not found'
}
$asTaskGeneric = Get-AsTaskGeneric

function Await($op, $type) {
    $m = $asTaskGeneric.MakeGenericMethod($type)
    $t = $m.Invoke($null, @($op))
    $t.Wait(-1) | Out-Null
    return $t.Result
}

[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage((New-Object Windows.Globalization.Language 'zh-Hans-CN'))
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $engine) { throw 'No OCR engine available' }

$res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])

$words = @()
foreach ($line in $res.Lines) {
    foreach ($w in $line.Words) {
        $r = $w.BoundingRect
        $words += [pscustomobject]@{
            text = $w.Text
            x = [math]::Round($r.X); y = [math]::Round($r.Y)
            w = [math]::Round($r.Width); h = [math]::Round($r.Height)
        }
    }
}
$lines = @()
foreach ($line in $res.Lines) {
    $minX = [double]::PositiveInfinity; $minY = [double]::PositiveInfinity
    $maxX = 0; $maxY = 0
    foreach ($w in $line.Words) {
        $r = $w.BoundingRect
        if ($r.X -lt $minX) { $minX = $r.X }
        if ($r.Y -lt $minY) { $minY = $r.Y }
        if (($r.X + $r.Width) -gt $maxX) { $maxX = $r.X + $r.Width }
        if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
    }
    if ($minX -eq [double]::PositiveInfinity) { $minX = 0; $minY = 0 }
    $lines += [pscustomobject]@{
        text = $line.Text
        x = [math]::Round($minX); y = [math]::Round($minY)
        w = [math]::Round($maxX - $minX); h = [math]::Round($maxY - $minY)
    }
}

$json = @{ words = $words; lines = $lines; text = $res.Text } | ConvertTo-Json -Depth 5 -Compress
[System.IO.File]::WriteAllText($Out, $json, (New-Object System.Text.UTF8Encoding($false)))
