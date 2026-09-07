// Data preparation and invocation: python3 src/phenology/plot_study_area.py
import Foundation
import AppKit
import PDFKit

let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let payload = try JSONSerialization.jsonObject(with: data) as! [String: Any]
let sites = payload["sites"] as! [[String: Any]]
let polygons = payload["polygons"] as! [[[[Double]]]]
let quality = payload["quality"] as! [String: Any]
let directory = URL(fileURLWithPath: CommandLine.arguments[2])
let output = directory.appendingPathComponent("study_area.pdf")
let W: CGFloat = 496, H: CGFloat = 590
let frame = CGRect(x: 12, y: 12, width: 472, height: 566)

// Spherical Lambert conformal conic; angles in radians, distances in km.
let rad = Double.pi / 180
let p1 = 43 * rad, p2 = 59 * rad, p0 = 50 * rad
let n = log(cos(p1) / cos(p2)) / log(tan(.pi/4+p2/2) / tan(.pi/4+p1/2))
let f = cos(p1) * pow(tan(.pi/4+p1/2), n) / n
let rho0 = 6371.0088 * f / pow(tan(.pi/4+p0/2), n)
func project(_ lon: Double, _ lat: Double) -> CGPoint {
    let rho = 6371.0088 * f / pow(tan(.pi/4+lat*rad/2), n)
    let theta = n * (lon-10) * rad
    return CGPoint(x: rho*sin(theta), y: rho0-rho*cos(theta))
}
let projected = sites.map { project($0["lon"] as! Double, $0["lat"] as! Double) }
let xmin = projected.map(\.x).min()!-340, xmax = projected.map(\.x).max()!+340
let ymin = projected.map(\.y).min()!-270, ymax = projected.map(\.y).max()!+230
let scale = min(frame.width/(xmax-xmin), frame.height/(ymax-ymin))
let cx = (xmin+xmax)/2, cy = (ymin+ymax)/2
func screen(_ p: CGPoint) -> CGPoint {
    CGPoint(x: frame.midX+(p.x-cx)*scale, y: frame.midY-(p.y-cy)*scale)
}
func point(_ lon: Double, _ lat: Double) -> CGPoint { screen(project(lon, lat)) }

var media = CGRect(x: 0, y: 0, width: W, height: H)
let ctx = CGContext(output as CFURL, mediaBox: &media,
                    [kCGPDFContextTitle: "Grapevine phenology observation sites"] as CFDictionary)!
ctx.beginPDFPage(nil)
ctx.translateBy(x: 0, y: H); ctx.scaleBy(x: 1, y: -1)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)
func color(_ hex: UInt32, _ alpha: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: CGFloat((hex>>16)&255)/255, green: CGFloat((hex>>8)&255)/255,
            blue: CGFloat(hex&255)/255, alpha: alpha)
}
let ink = color(0x27333D), muted = color(0x626C72)
let yearColors = [0xBDD7E7, 0x7AAED0, 0x4389B5, 0x236192, 0x103B63].map { color(UInt32($0)) }
let legendLabels = ["1–5", "6–10", "11–20", "21–40", ">40"]
let legendSize: CGFloat = 15
func yearClass(_ years: Int) -> Int {
    precondition(years >= 1)
    return years <= 5 ? 0 : years <= 10 ? 1 : years <= 20 ? 2 : years <= 40 ? 3 : 4
}
func text(_ s: String, _ x: CGFloat, _ y: CGFloat, size: CGFloat = 10,
          weight: NSFont.Weight = .regular, shade: NSColor = ink, center: Bool = false,
          halo: Bool = false) {
    var attrs: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: size, weight: weight), .foregroundColor: shade]
    let string = NSAttributedString(string: s, attributes: attrs)
    let extent = string.size()
    let origin = CGPoint(x: center ? x-extent.width/2 : x, y: y)
    precondition(origin.x >= 0 && origin.y >= 0 && origin.x+extent.width <= W && origin.y+extent.height <= H,
                 "Label outside page: \(s)")
    if halo {
        attrs[.strokeColor] = NSColor.white
        attrs[.strokeWidth] = -4
        NSAttributedString(string: s, attributes: attrs).draw(at: origin)
        string.draw(at: origin) // Restore solid glyph interiors over the white halo.
    } else { string.draw(at: origin) }
}
func line(_ points: [CGPoint], shade: NSColor, width: CGFloat) {
    guard let first = points.first else { return }
    ctx.setStrokeColor(shade.cgColor); ctx.setLineWidth(width)
    ctx.move(to: first)
    for p in points.dropFirst() { ctx.addLine(to: p) }
    ctx.strokePath()
}
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(media)
ctx.saveGState(); ctx.clip(to: frame)
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(frame)
for rings in polygons {
    ctx.beginPath()
    for ring in rings {
        guard let first = ring.first else { continue }
        ctx.move(to: point(first[0], first[1]))
        for xy in ring.dropFirst() { ctx.addLine(to: point(xy[0], xy[1])) }
        ctx.closePath()
    }
    ctx.setFillColor(color(0xF0F1EF).cgColor)
    ctx.setStrokeColor(color(0xB1B8BB).cgColor); ctx.setLineWidth(0.45)
    ctx.drawPath(using: .eoFillStroke)
}
ctx.setLineDash(phase: 0, lengths: [2, 3])
for lon in stride(from: -15, through: 35, by: 5) {
    line(stride(from: 30.0, through: 72, by: 0.2).map { point(Double(lon), $0) },
         shade: color(0xCFD5D8), width: 0.35)
}
for lat in stride(from: 35, through: 70, by: 5) {
    line(stride(from: -20.0, through: 40, by: 0.2).map { point($0, Double(lat)) },
         shade: color(0xCFD5D8), width: 0.35)
}
ctx.setLineDash(phase: 0, lengths: [])
// Opaque colour encodes availability, never point-overlap density.
let drawOrder = sites.indices.sorted {
    let a = sites[$0]["n_years"] as! Int, b = sites[$1]["n_years"] as! Int
    return a == b ? $0 < $1 : a < b
}
for index in drawOrder {
    let s = screen(projected[index])
    precondition(frame.insetBy(dx: 2, dy: 2).contains(s), "Site outside frame")
    ctx.setFillColor(yearColors[yearClass(sites[index]["n_years"] as! Int)].cgColor)
    ctx.setStrokeColor(color(0x476780).cgColor); ctx.setLineWidth(0.18)
    ctx.addEllipse(in: CGRect(x: s.x-1.45, y: s.y-1.45, width: 2.9, height: 2.9))
    ctx.drawPath(using: .fillStroke)
}
// Labels are geographical annotations, not replacements for source country codes.
let labels: [(String, Double, Double)] = [
    ("FRANCE", 1.5, 44.3), ("GERMANY", 11.6, 53.2), ("SPAIN", -3.5, 40.1),
    ("SWEDEN", 14.1, 60.7), ("NORWAY", 7.1, 61.7), ("FINLAND", 26.4, 62.4),
    ("POLAND", 19.3, 52.2), ("ITALY", 12.4, 42.1), ("AUSTRIA", 13.8, 47.3),
    ("SLOVAKIA", 20.7, 49.3),
    ("CZECHIA", 16, 50.0), ("HUNGARY", 20, 46.9), ("CROATIA", 16, 45.2),
    ("UNITED KINGDOM", -3, 54.6), ("DENMARK", 9.1, 56.4),
    ("ROMANIA", 26, 45.5)
]
for (label, lon, lat) in labels {
    let p = point(lon, lat)
    if frame.insetBy(dx: 36, dy: 12).contains(p) {
        text(label, p.x, p.y-4, size: 9, weight: .medium, shade: muted, center: true, halo: true)
    }
}
// Small states use ISO codes to avoid long labels crowding central Europe.
for (label, lon, lat) in [("LU",6.1,49.8), ("CH",8.1,46.8), ("SI",14.6,46.0), ("BA",18.0,44.0), ("ME",19.3,42.7)] {
    let p = point(lon,lat)
    if frame.insetBy(dx: 20, dy: 12).contains(p) {
        text(label, p.x, p.y, size: 8.5, weight: .medium, shade: muted, center: true, halo: true)
    }
}
// Graticule labels along visible meridians/parallels, placed in ocean where possible.
for lat in [40.0, 45, 50, 55, 60] {
    // Northern labels stay clear of the large upper-left legend.
    let p = point(lat >= 55 ? 30 : -10,lat)
    if frame.insetBy(dx: 20,dy: 10).contains(p) {
        text("\(Int(lat))°N", p.x, p.y, size: 8, shade: muted, halo: true)
    }
}
for lon in [0.0, 10, 20] {
    let p = point(lon,36.6)
    if frame.insetBy(dx: 20,dy: 10).contains(p) {
        text(lon == 0 ? "0°" : "\(Int(lon))°E", p.x, p.y, size: 8, shade: muted, center: true)
    }
}
ctx.restoreGState()
ctx.setStrokeColor(color(0xB1B8BB).cgColor); ctx.setLineWidth(0.5); ctx.stroke(frame)
// All legend typography is 15 pt at the exported PDF's native size.
let lx = frame.minX+16, ly = frame.minY+18
let legendBox = CGRect(x: lx-6, y: ly-5, width: 143, height: 178)
precondition(projected.allSatisfy { !legendBox.insetBy(dx: -2, dy: -2).contains(screen($0)) },
             "Legend overlaps an observed site")
text("Years with data", lx, ly, size: legendSize, weight: .medium, halo: true)
let yearRange = "(\((quality["first_date"] as! String).prefix(4))–\((quality["last_date"] as! String).prefix(4)))"
text(yearRange, lx, ly+21, size: legendSize, halo: true)
for (index, label) in legendLabels.enumerated() {
    let y = ly+51+CGFloat(index)*23
    ctx.setFillColor(yearColors[index].cgColor)
    ctx.setStrokeColor(color(0x476780).cgColor); ctx.setLineWidth(0.35)
    ctx.addEllipse(in: CGRect(x: lx+1, y: y+5, width: 7, height: 7))
    ctx.drawPath(using: .fillStroke)
    text(label, lx+19, y, size: legendSize, halo: true)
}

NSGraphicsContext.restoreGraphicsState()
ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
precondition(page.bounds(for: .mediaBox).size == media.size)
let contents = page.string ?? ""
precondition(!contents.contains("Grapevine phenology observation sites"), "Unwanted figure title")
for label in ["Years with data", yearRange] + legendLabels {
    precondition(contents.contains(label), "Missing legend label: \(label)")
    let selections = pdf.findString(label, withOptions: [])
    precondition(!selections.isEmpty)
    for selection in selections {
        let fonts = selection.attributedString!
        fonts.enumerateAttribute(.font, in: NSRange(location: 0, length: fonts.length)) { value, _, _ in
            if let font = value as? NSFont {
                precondition(abs(font.pointSize-legendSize)<0.1, "Legend text is not 15 pt")
            }
        }
    }
}
let preview = page.thumbnail(of: NSSize(width: W*3, height: H*3), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: preview.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: directory.appendingPathComponent("study_area.png"))
print("Exported one-page vector PDF and PNG; all \(sites.count) sites are inside the map frame.")
