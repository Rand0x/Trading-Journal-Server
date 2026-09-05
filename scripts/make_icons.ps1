Add-Type -AssemblyName System.Drawing

function Create-RoundedRectanglePath([float]$x, [float]$y, [float]$width, [float]$height, [float]$radius) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = $radius * 2.0
    $path.AddArc($x, $y, $d, $d, 180, 90)
    $path.AddArc($x + $width - $d, $y, $d, $d, 270, 90)
    $path.AddArc($x + $width - $d, $y + $height - $d, $d, $d, 0, 90)
    $path.AddArc($x, $y + $height - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return $path
}

function Render-Favicon([int]$size, [string]$outputPath) {
    $bmp = New-Object System.Drawing.Bitmap($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)

    [float]$scale = [float]$size / 64.0
    [float]$pad = [Math]::Max(1.0, 2.0 * $scale)
    [float]$rectWidth = [float]$size - (2.0 * $pad)
    [float]$rectHeight = [float]$size - (2.0 * $pad)
    [float]$corner = [Math]::Max(2.0, 14.0 * $scale)

    # Base rounded container
    $bgPath = Create-RoundedRectanglePath $pad $pad $rectWidth $rectHeight $corner
    $pStart = New-Object System.Drawing.PointF(0, 0)
    $pEnd = New-Object System.Drawing.PointF([float]$size, [float]$size)
    $cBg1 = [System.Drawing.Color]::FromArgb(255, 15, 23, 42)
    $cBg2 = [System.Drawing.Color]::FromArgb(255, 2, 6, 23)
    $bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($pStart, $pEnd, $cBg1, $cBg2)
    $g.FillPath($bgBrush, $bgPath)

    # Border gradient
    $cBrd1 = [System.Drawing.Color]::FromArgb(255, 59, 130, 246)
    $cBrd2 = [System.Drawing.Color]::FromArgb(255, 16, 185, 129)
    $borderBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($pStart, $pEnd, $cBrd1, $cBrd2)
    [float]$borderWidth = [Math]::Max(1.0, 2.5 * $scale)
    $borderPen = New-Object System.Drawing.Pen($borderBrush, $borderWidth)
    $g.DrawPath($borderPen, $bgPath)

    # Candlestick 1: Red (Pullback)
    $cRed = [System.Drawing.Color]::FromArgb(255, 239, 68, 68)
    $redPen = New-Object System.Drawing.Pen($cRed, [Math]::Max(1.0, 2.0 * $scale))
    $redBrush = New-Object System.Drawing.SolidBrush($cRed)
    $g.DrawLine($redPen, 16.0 * $scale, 24.0 * $scale, 16.0 * $scale, 48.0 * $scale)
    $g.FillRectangle($redBrush, 13.0 * $scale, 28.0 * $scale, [Math]::Max(2.0, 6.0 * $scale), [Math]::Max(3.0, 13.0 * $scale))

    # Candlestick 2: Green (Middle)
    $cGreen = [System.Drawing.Color]::FromArgb(255, 16, 185, 129)
    $greenPen = New-Object System.Drawing.Pen($cGreen, [Math]::Max(1.0, 2.0 * $scale))
    $greenBrush = New-Object System.Drawing.SolidBrush($cGreen)
    $g.DrawLine($greenPen, 32.0 * $scale, 16.0 * $scale, 32.0 * $scale, 44.0 * $scale)
    $g.FillRectangle($greenBrush, 29.0 * $scale, 21.0 * $scale, [Math]::Max(2.0, 6.0 * $scale), [Math]::Max(3.0, 17.0 * $scale))

    # Candlestick 3: Green (Breakout)
    $g.DrawLine($greenPen, 48.0 * $scale, 10.0 * $scale, 48.0 * $scale, 36.0 * $scale)
    $g.FillRectangle($greenBrush, 45.0 * $scale, 14.0 * $scale, [Math]::Max(2.0, 6.0 * $scale), [Math]::Max(3.0, 15.0 * $scale))

    # Trend line
    $pTrendStart = New-Object System.Drawing.PointF(0, [float]$size)
    $pTrendEnd = New-Object System.Drawing.PointF([float]$size, 0)
    $cTrend1 = [System.Drawing.Color]::FromArgb(255, 56, 189, 248)
    $cTrend2 = [System.Drawing.Color]::FromArgb(255, 52, 211, 153)
    $trendBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($pTrendStart, $pTrendEnd, $cTrend1, $cTrend2)
    [float]$trendWidth = [Math]::Max(1.5, 3.0 * $scale)
    $trendPen = New-Object System.Drawing.Pen($trendBrush, $trendWidth)
    $trendPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $trendPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $trendPen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round

    [System.Drawing.PointF[]]$pts = @(
        (New-Object System.Drawing.PointF((12.0 * $scale), (46.0 * $scale))),
        (New-Object System.Drawing.PointF((24.0 * $scale), (35.0 * $scale))),
        (New-Object System.Drawing.PointF((34.0 * $scale), (39.0 * $scale))),
        (New-Object System.Drawing.PointF((52.0 * $scale), (14.0 * $scale)))
    )
    $g.DrawLines($trendPen, $pts)

    # Apex glowing node
    $cApex = [System.Drawing.Color]::FromArgb(255, 52, 211, 153)
    $apexBrush = New-Object System.Drawing.SolidBrush($cApex)
    [float]$r = [Math]::Max(2.0, 4.0 * $scale)
    [float]$cx = 52.0 * $scale
    [float]$cy = 14.0 * $scale
    $g.FillEllipse($apexBrush, $cx - $r, $cy - $r, $r * 2.0, $r * 2.0)

    $centerBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
    [float]$r2 = [Math]::Max(1.0, 2.0 * $scale)
    $g.FillEllipse($centerBrush, $cx - $r2, $cy - $r2, $r2 * 2.0, $r2 * 2.0)

    $bmp.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose()
    $bmp.Dispose()
}

Render-Favicon 16 server/static/favicon-16x16.png
Render-Favicon 32 server/static/favicon-32x32.png
Render-Favicon 48 server/static/favicon-48x48.png
Render-Favicon 180 server/static/apple-touch-icon.png
Write-Output PNG icons successfully created.
