// Data preparation and invocation: python3 src/phenology/plot_study_area.py
// Text, sites, graticules and borders remain vector objects in the PDF.
import Foundation
import AppKit
import PDFKit

precondition(CommandLine.arguments.count == 3, "Usage: draw_map.swift payload.json output-directory")
let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let payload = try JSONSerialization.jsonObject(with: data) as! [String: Any]
let sites = payload["sites"] as! [[String: Any]]
let quality = payload["quality"] as! [String: Any]
let polygons = payload["polygons"] as! [[[[Double]]]]
let panels = payload["panels"] as! [[String: Any]]
let elevationStops = payload["elevation_colours"] as! [[String: Any]]
let directory = URL(fileURLWithPath: CommandLine.arguments[2])
let output = directory.appendingPathComponent("study_area.pdf")
let W: CGFloat = 180 * 72 / 25.4, H: CGFloat = 132 * 72 / 25.4

// Spherical Lambert conformal conic, exactly matching Python; distances in metres.
let rad = Double.pi / 180
let p1 = 43 * rad, p2 = 59 * rad, p0 = 50 * rad
let n = log(cos(p1) / cos(p2)) / log(tan(.pi/4+p2/2) / tan(.pi/4+p1/2))
let f = cos(p1) * pow(tan(.pi/4+p1/2), n) / n
let radius = 6371008.8
let rho0 = radius * f / pow(tan(.pi/4+p0/2), n)
func project(_ lon: Double, _ lat: Double) -> CGPoint {
    let rho = radius * f / pow(tan(.pi/4+lat*rad/2), n)
    let theta = n * (lon-10) * rad
    return CGPoint(x: rho*sin(theta), y: rho0-rho*cos(theta))
}
let projected = sites.map { project($0["lon"] as! Double, $0["lat"] as! Double) }
func color(_ hex: UInt32, _ alpha: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex>>16)&255)/255, green: CGFloat((hex>>8)&255)/255,
            blue: CGFloat(hex&255)/255, alpha: alpha)
}
func hexColor(_ value: String) -> NSColor {
    color(UInt32(value.replacingOccurrences(of: "#", with: ""), radix: 16)!)
}
let ink = color(0x263945), muted = color(0x56636B)
let yearColors = [0xBDD7E7, 0x7AAED0, 0x4389B5, 0x236192, 0x103B63].map { color(UInt32($0)) }
let legendLabels = ["1–5", "6–10", "11–20", "21–40", ">40"]
func yearClass(_ years: Int) -> Int {
    precondition(years >= 1)
    return years <= 5 ? 0 : years <= 10 ? 1 : years <= 20 ? 2 : years <= 40 ? 3 : 4
}
var media = CGRect(x: 0, y: 0, width: W, height: H)
let ctx = CGContext(output as CFURL, mediaBox: &media,
                    [kCGPDFContextTitle: "Grapevine phenology observation sites"] as CFDictionary)!
ctx.beginPDFPage(nil)
ctx.translateBy(x: 0, y: H); ctx.scaleBy(x: 1, y: -1)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)

// No stroke/halo attributes: every annotation remains ordinary editable PDF text.
func labelSize(_ s: String, size: CGFloat = 8, bold: Bool = false) -> CGSize {
    NSAttributedString(string: s, attributes: [
        .font: NSFont(name: bold ? "Helvetica-Bold" : "Helvetica", size: size)!
    ]).size()
}
func text(_ s: String, _ x: CGFloat, _ y: CGFloat, size: CGFloat = 8,
          bold: Bool = false, shade: NSColor = ink, center: Bool = false,
          background: Bool = false) {
    let font = NSFont(name: bold ? "Helvetica-Bold" : "Helvetica", size: size)!
    let string = NSAttributedString(string: s, attributes: [.font: font, .foregroundColor: shade])
    let extent = string.size()
    let origin = CGPoint(x: center ? x-extent.width/2 : x, y: y)
    precondition(origin.x >= 0 && origin.y >= 0 && origin.x+extent.width <= W && origin.y+extent.height <= H,
                 "Label outside page: \(s)")
    if background {
        ctx.setFillColor(color(0xFAFAF7).cgColor)
        ctx.fill(CGRect(origin: origin, size: extent).insetBy(dx: -1.1, dy: -0.5))
    }
    string.draw(at: origin)
}
func line(_ points: [CGPoint], shade: NSColor, width: CGFloat) {
    guard let first = points.first else { return }
    ctx.beginPath(); ctx.setStrokeColor(shade.cgColor); ctx.setLineWidth(width)
    ctx.move(to: first)
    for p in points.dropFirst() { ctx.addLine(to: p) }
    ctx.strokePath()
}
func marker(_ p: CGPoint, radius: CGFloat, shade: NSColor) {
    ctx.setFillColor(shade.cgColor)
    ctx.setStrokeColor(NSColor.white.cgColor); ctx.setLineWidth(0.28)
    ctx.addEllipse(in: CGRect(x: p.x-radius, y: p.y-radius, width: radius*2, height: radius*2))
    ctx.drawPath(using: .fillStroke)
}
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(media)
precondition(panels.count == 2, "Expected European overview and core detail panels")
var overviewIndices = Set<Int>()
var frames: [CGRect] = []
for (panelIndex, panel) in panels.enumerated() {
    let dimensions = panel["frame"] as! [Double]
    let frame = CGRect(x: dimensions[0], y: dimensions[1], width: dimensions[2], height: dimensions[3])
    frames.append(frame)
    precondition(media.contains(frame), "Panel is outside the page")
    let bounds = panel["bounds"] as! [Double]
    let xscale = frame.width / (bounds[2]-bounds[0])
    let yscale = frame.height / (bounds[3]-bounds[1])
    precondition(abs(xscale/yscale-1) < 0.0001, "Map projection must not be stretched")
    func screen(_ p: CGPoint) -> CGPoint {
        CGPoint(x: frame.minX+(p.x-bounds[0])*xscale, y: frame.maxY-(p.y-bounds[1])*yscale)
    }
    func point(_ lon: Double, _ lat: Double) -> CGPoint { screen(project(lon, lat)) }
    let indices = panel["site_indices"] as! [Int]
    precondition(Set(indices).count == indices.count, "Duplicated site index in panel")
    if panelIndex == 0 { overviewIndices = Set(indices) }
    let backgroundPath = panel["background"] as! String
    let raster = NSImage(contentsOfFile: backgroundPath)!
    let rasterCG = raster.cgImage(forProposedRect: nil, context: nil, hints: nil)!
    ctx.saveGState(); ctx.clip(to: frame)
    // CGImage has its own bottom-up drawing convention, unlike the top-down frame.
    ctx.saveGState()
    ctx.translateBy(x: frame.minX, y: frame.maxY); ctx.scaleBy(x: 1, y: -1)
    ctx.interpolationQuality = .high
    ctx.draw(rasterCG, in: CGRect(x: 0, y: 0, width: frame.width, height: frame.height))
    ctx.restoreGState()

    // Country outlines are vector paths over the embedded elevation/hillshade image.
    for rings in polygons {
        ctx.beginPath()
        for ring in rings {
            guard let first = ring.first else { continue }
            ctx.move(to: point(first[0], first[1]))
            for xy in ring.dropFirst() { ctx.addLine(to: point(xy[0], xy[1])) }
            ctx.closePath()
        }
        ctx.setStrokeColor(color(0xA1AAA7).cgColor)
        ctx.setLineWidth(panelIndex == 0 ? 0.30 : 0.40)
        ctx.strokePath()
    }
    let lonStep = panelIndex == 0 ? 10 : 5
    let latStep = panelIndex == 0 ? 5 : 2
    ctx.setLineDash(phase: 0, lengths: [1.3, 2.5])
    for lon in stride(from: -30, through: 50, by: lonStep) {
        line(stride(from: 25.0, through: 75, by: 0.2).map { point(Double(lon), $0) },
             shade: color(0xABB5B5, 0.60), width: 0.25)
    }
    for lat in stride(from: 30, through: 74, by: latStep) {
        line(stride(from: -35.0, through: 55, by: 0.2).map { point($0, Double(lat)) },
             shade: color(0xABB5B5, 0.60), width: 0.25)
    }
    ctx.setLineDash(phase: 0, lengths: [])
    let overviewLabels: [(String, Double, Double)] = [
        ("FRANCE", 2.4, 46.5), ("GERMANY", 14.1, 53.9), ("SPAIN", -1.8, 39.4),
        ("ITALY", 13.0, 42.0), ("POLAND", 20.0, 52.5), ("AUSTRIA", 14.0, 47.0),
        ("UNITED KINGDOM", -3.4, 55.0), ("SWEDEN", 15.2, 60.8), ("ROMANIA", 25.0, 45.5)
    ]
    let detailLabels: [(String, Double, Double)] = [
        ("FRANCE", 1.4, 45.6), ("SWITZERLAND", 7.6, 46.0),
        ("BELGIUM", 4.3, 50.6), ("ITALY", 10.3, 44.8)
    ]
    // Labels precede sites so no annotation obscures an observed marker.
    var countryLabelBounds: [CGRect] = []
    for (label, lon, lat) in panelIndex == 0 ? overviewLabels : detailLabels {
        let p = point(lon, lat)
        let extent = labelSize(label)
        let labelBounds = CGRect(x: p.x-extent.width/2, y: p.y-extent.height/2,
                                 width: extent.width, height: extent.height)
        // Expanded marker boxes include the outline and a small visual clearance.
        // Detail Germany has no clear anchor and is already labelled in the overview.
        let markerExtent: CGFloat = (panelIndex == 0 ? 1.05 : 1.55)+0.14+0.15
        let clearOfMarkers = indices.allSatisfy { index in
            let sitePoint = screen(projected[index])
            let markerBounds = CGRect(x: sitePoint.x-markerExtent, y: sitePoint.y-markerExtent,
                                      width: markerExtent*2, height: markerExtent*2)
            return !labelBounds.intersects(markerBounds)
        }
        let clearOfLabels = countryLabelBounds.allSatisfy { !$0.insetBy(dx: -2, dy: -2).intersects(labelBounds) }
        if frame.insetBy(dx: 2, dy: 2).contains(labelBounds) && clearOfLabels && (panelIndex == 0 || clearOfMarkers) {
            text(label, p.x, labelBounds.minY, shade: muted, center: true)
            countryLabelBounds.append(labelBounds)
        }
    }
    if panelIndex == 0 {
        // Local geographic north under the Lambert projection (3°W, 61°N).
        let base = point(-3, 61), north = point(-3, 61.2)
        let distance = hypot(north.x-base.x, north.y-base.y)
        let ux = (north.x-base.x)/distance, uy = (north.y-base.y)/distance
        let tip = CGPoint(x: base.x+15.45*ux, y: base.y+15.45*uy)
        line([base, tip], shade: ink, width: 1.09)
        ctx.beginPath(); ctx.move(to: tip)
        ctx.addLine(to: CGPoint(x: tip.x-4.55*ux-2*uy, y: tip.y-4.55*uy+2*ux))
        ctx.addLine(to: CGPoint(x: tip.x-4.55*ux+2*uy, y: tip.y-4.55*uy-2*ux))
        ctx.closePath(); ctx.setFillColor(ink.cgColor); ctx.fillPath()
        text("N", tip.x, tip.y-11, size: 8, bold: true, center: true)
        let detailBounds = panels[1]["bounds"] as! [Double]
        let edge = [
            screen(CGPoint(x: detailBounds[0], y: detailBounds[1])),
            screen(CGPoint(x: detailBounds[2], y: detailBounds[1])),
            screen(CGPoint(x: detailBounds[2], y: detailBounds[3])),
            screen(CGPoint(x: detailBounds[0], y: detailBounds[3]))
        ]
        ctx.setLineDash(phase: 0, lengths: [3, 2])
        line(edge + [edge[0]], shade: color(0x526670), width: 0.65)
        ctx.setLineDash(phase: 0, lengths: [])
    }
    // Opaque colour encodes distinct years, never marker-overlap density.
    let ordered = indices.sorted {
        let a = sites[$0]["n_years"] as! Int, b = sites[$1]["n_years"] as! Int
        return a == b ? $0 < $1 : a < b
    }
    for index in ordered {
        precondition(sites.indices.contains(index), "Invalid site index")
        let p = screen(projected[index])
        precondition(frame.insetBy(dx: -0.01, dy: -0.01).contains(p), "Site outside its panel")
        marker(p, radius: panelIndex == 0 ? 1.05 : 1.55,
               shade: yearColors[yearClass(sites[index]["n_years"] as! Int)])
    }
    // Label the actual graticule intersections with the left and bottom panel edges.
    for lat in stride(from: 30, through: 74, by: latStep) {
        let samples = stride(from: -35.0, through: 55, by: 0.025).map { point($0, Double(lat)) }
        if let p = samples.min(by: { abs($0.x-frame.minX) < abs($1.x-frame.minX) }),
           p.y > frame.minY+10 && p.y < frame.maxY-14 {
            text("\(lat)°N", frame.minX+3, p.y-4.5, shade: muted, background: true)
        }
    }
    for lon in stride(from: -30, through: 50, by: lonStep) {
        let samples = stride(from: 25.0, through: 75, by: 0.025).map { point(Double(lon), $0) }
        if let p = samples.min(by: { abs($0.y-frame.maxY) < abs($1.y-frame.maxY) }),
           p.x > frame.minX+22 && p.x < frame.maxX-16 {
            let label = lon == 0 ? "0°" : "\(abs(lon))°\(lon < 0 ? "W" : "E")"
            text(label, p.x, frame.maxY-12, shade: muted, center: true, background: true)
        }
    }
    ctx.restoreGState()
    ctx.setStrokeColor(color(0x9BA7AD).cgColor); ctx.setLineWidth(0.45); ctx.stroke(frame)
    text("(\(panel["id"] as! String))", frame.minX, frame.minY-16, size: 9, bold: true)

    // A local ground-distance scale at each panel's centre latitude.
    // LCC local scale k = n*rho/(R*cos(phi)); recover phi from the projected centre.
    let projectedX = (bounds[0]+bounds[2])/2
    let projectedY = (bounds[1]+bounds[3])/2
    let rho = hypot(projectedX, rho0-projectedY)
    let latitude = 2*atan(pow(radius*f/rho, 1/n)) - .pi/2
    let localScale = n*rho/(radius*cos(latitude))
    let scaleKM = panel["scale_km"] as! Int
    let barLength = CGFloat(scaleKM*1000)*xscale*localScale
    precondition(barLength < frame.width-30, "Scale bar too long")
    let barX = frame.minX+12, barY = frame.maxY+10
    line([CGPoint(x: barX,y: barY), CGPoint(x: barX+barLength,y: barY)], shade: ink, width: 0.7)
    for x in [barX, barX+barLength/2, barX+barLength] {
        line([CGPoint(x: x,y: barY-2),CGPoint(x: x,y: barY+2)],shade: ink,width: 0.6)
    }
    text("0",barX,barY+4,center: true)
    text("\(scaleKM) km",barX+barLength,barY+4,center: true)
}
precondition(overviewIndices == Set(sites.indices), "Overview must include every site exactly once")

let detail = frames[1]
let overview = frames[0]
let yearsX = overview.minX+5
let yearsY = overview.maxY+28
let yearRange = "\((quality["first_date"] as! String).prefix(4))–\((quality["last_date"] as! String).prefix(4))"
let yearHeadingWidth = labelSize("Years with data").width
text("Years with data", yearsX, yearsY)
text("(\(yearRange))", yearsX+yearHeadingWidth+8, yearsY, shade: muted)
let legendGap = (overview.width-10)/5
for (index,label) in legendLabels.enumerated() {
    let x = yearsX+CGFloat(index)*legendGap
    marker(CGPoint(x: x+2,y: yearsY+20), radius: 1.8, shade: yearColors[index])
    precondition(labelSize(label).width+8 < legendGap, "Year-legend labels overlap")
    text(label,x+8,yearsY+16)
}
let legendX = detail.minX+5
let terrainY = detail.maxY+39
text("Elevation (m)",legendX,terrainY)
let bar = CGRect(x: legendX,y: terrainY+15,width: detail.width-10,height: 7)
let stopValues = elevationStops.map { $0["metres"] as! Double }
precondition(stopValues.count >= 2 && zip(stopValues,stopValues.dropFirst()).allSatisfy { $0 < $1 })
let minimum = stopValues.first!, maximum = stopValues.last!
let locations = stopValues.map { CGFloat(($0-minimum)/(maximum-minimum)) }
let colors = elevationStops.map { hexColor($0["hex"] as! String).cgColor }
let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: colors as CFArray,
                          locations: locations)!
ctx.saveGState(); ctx.clip(to: bar)
ctx.drawLinearGradient(gradient, start: CGPoint(x: bar.minX,y: bar.midY),
                       end: CGPoint(x: bar.maxX,y: bar.midY),options: [])
ctx.restoreGState()
ctx.setStrokeColor(color(0x9BA7AD).cgColor); ctx.setLineWidth(0.3);ctx.stroke(bar)
// Keep ticks legible even when the colour ramp has closely spaced lowland stops.
var lastTickRight: CGFloat = -1000
let finalTickLeft = bar.maxX-labelSize(String(Int(maximum))).width/2
for (index,value) in stopValues.enumerated() {
    let x = bar.minX+locations[index]*bar.width
    let label = String(Int(value))
    let halfWidth = labelSize(label).width/2
    guard index == 0 || index == stopValues.count-1 ||
          (x-halfWidth-lastTickRight > 8 && finalTickLeft-x-halfWidth > 8) else { continue }
    precondition(x-halfWidth-lastTickRight > 5, "Elevation-legend labels overlap")
    line([CGPoint(x:x,y:bar.maxY),CGPoint(x:x,y:bar.maxY+2)],shade:muted,width:0.3)
    text(label,x,bar.maxY+4,shade:muted,center:true)
    lastTickRight=x+halfWidth
}
NSGraphicsContext.restoreGraphicsState()
ctx.endPDFPage(); ctx.closePDF()

let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
let pageSize = page.bounds(for: .mediaBox).size
precondition(abs(pageSize.width-W)<0.01 && abs(pageSize.height-H)<0.01, "Incorrect 180 × 132 mm page")
let contents = page.string ?? ""
precondition(!contents.contains("Grapevine phenology observation sites"), "Unwanted figure title")
for label in ["Years with data", yearRange, "Elevation (m)"] + legendLabels {
    precondition(contents.contains(label), "Missing editable legend label: \(label)")
}
for panel in panels {
    precondition(contents.contains("(\(panel["id"] as! String))"), "Missing parenthesized panel label")
    precondition(!contents.contains(panel["title"] as! String), "Unwanted subplot title")
}
var extractedFonts = Set<String>(), extractedSizes = Set<Double>()
if let attributed = page.attributedString {
    attributed.enumerateAttribute(.font, in: NSRange(location:0,length:attributed.length)) { value,_,_ in
        if let font = value as? NSFont {
            extractedFonts.insert(font.fontName)
            extractedSizes.insert((Double(font.pointSize)*100).rounded()/100)
            precondition(font.fontName.contains("Helvetica"), "Unexpected font: \(font.fontName)")
            precondition(abs(font.pointSize-8)<0.05 || abs(font.pointSize-9)<0.05, "Unexpected text size")
            if abs(font.pointSize-9)<0.05 {
                precondition(font.fontName.contains("Bold"), "Panel label must be bold")
            }
        }
    }
}
let typography: [String: Any] = [
    "page_width_pt": pageSize.width, "page_height_pt": pageSize.height,
    "fonts": extractedFonts.sorted(), "font_sizes_pt": extractedSizes.sorted(),
    "ordinary_text_pt": 8, "panel_letters_pt": 9,
    "panel_labels": ["(a)", "(b)"], "subplot_titles": false,
    "all_sites_rendered": overviewIndices.count,
    "legend_collision_checks": "Measured 8 pt text bounds; nonoverlapping year classes and elevation ticks"
]
try JSONSerialization.data(withJSONObject: typography, options: [.prettyPrinted, .sortedKeys]).write(
    to: directory.appendingPathComponent("typography_verification.json"))
func exportRaster(dpi: CGFloat, type: NSBitmapImageRep.FileType, name: String) throws {
    let pixelsWide = Int((W*dpi/72).rounded()), pixelsHigh = Int((H*dpi/72).rounded())
    let bitmap = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:pixelsWide,pixelsHigh:pixelsHigh,
                                 bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,
                                 colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    let graphics = NSGraphicsContext(bitmapImageRep:bitmap)!
    let rasterContext = graphics.cgContext
    rasterContext.setFillColor(NSColor.white.cgColor)
    rasterContext.fill(CGRect(x:0,y:0,width:pixelsWide,height:pixelsHigh))
    rasterContext.scaleBy(x:CGFloat(pixelsWide)/W,y:CGFloat(pixelsHigh)/H)
    page.draw(with:.mediaBox,to:rasterContext)
    bitmap.size = NSSize(width:W,height:H)
    let properties: [NSBitmapImageRep.PropertyKey:Any] = type == .tiff ? [.compressionMethod:NSBitmapImageRep.TIFFCompression.lzw.rawValue] : [:]
    try bitmap.representation(using:type,properties:properties)!.write(to:directory.appendingPathComponent(name))
}
try exportRaster(dpi:300,type:.png,name:"study_area.png")
try exportRaster(dpi:600,type:.tiff,name:"study_area.tiff")
print("Exported 180 × 132 mm PDF with editable Helvetica text, 300 dpi PNG and 600 dpi TIFF; overview contains all \(sites.count) sites.")
