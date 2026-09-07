// Run from the repository root:
// swift -module-cache-path /tmp/grape-workflow-swift-cache src/phenology/draw_workflow.swift
// Run from the repository root with Swift; exports to fig/workflow/.
import Foundation
import AppKit
import PDFKit

let output = URL(fileURLWithPath: "fig/workflow/workflow.pdf")
let W: CGFloat = 595.2756, H: CGFloat = 841.8898 // Original A4 layout coordinates
let modelExtraHeight: CGFloat = 12
let exportHeight: CGFloat = 728 + modelExtraHeight, topTrim: CGFloat = 73
var media = CGRect(x: 0, y: 0, width: W, height: exportHeight)
let ctx = CGContext(output as CFURL, mediaBox: &media, [
    kCGPDFContextTitle: "Grapevine phenology modelling workflow",
    kCGPDFContextSubject: "Forcing, chilling and residual learning; calibration and independent testing"
] as CFDictionary)!
ctx.beginPDFPage(nil)
ctx.translateBy(x: 0, y: exportHeight)
ctx.scaleBy(x: 1, y: -1)
ctx.translateBy(x: 0, y: -topTrim)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)

func color(_ hex: String) -> NSColor {
    let v = UInt32(hex, radix: 16)!
    return NSColor(srgbRed: CGFloat((v >> 16) & 255) / 255,
                   green: CGFloat((v >> 8) & 255) / 255,
                   blue: CGFloat(v & 255) / 255, alpha: 1)
}
let ink = color("243342"), muted = color("596571"), border = color("D8DEE3")
let blue = color("326C9C"), ochre = color("9A621A")
let purple = color("73549B"), green = color("23745E"), rose = color("A04F64")
let white = NSColor.white

func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat,
         fill: NSColor = .white, stroke: NSColor = border,
         radius: CGFloat = 5, line: CGFloat = 0.6, dash: Bool = false) {
    ctx.saveGState()
    ctx.setLineWidth(line)
    if dash { ctx.setLineDash(phase: 0, lengths: [3, 2]) }
    ctx.setFillColor(fill.cgColor); ctx.setStrokeColor(stroke.cgColor)
    ctx.addPath(CGPath(roundedRect: CGRect(x: x, y: y, width: w, height: h),
                       cornerWidth: radius, cornerHeight: radius, transform: nil))
    ctx.drawPath(using: .fillStroke)
    ctx.restoreGState()
}
func text(_ s: String, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat,
          size: CGFloat = 10.5, weight: NSFont.Weight = .regular,
          color: NSColor = ink, align: NSTextAlignment = .left, height: CGFloat = 16) {
    let p = NSMutableParagraphStyle()
    p.alignment = align; p.lineSpacing = 1
    let a = NSAttributedString(string: s, attributes: [
        .font: NSFont.systemFont(ofSize: size, weight: weight),
        .foregroundColor: color, .paragraphStyle: p
    ])
    let needed = a.boundingRect(with: NSSize(width: w, height: 2000),
                               options: [.usesLineFragmentOrigin, .usesFontLeading]).height
    precondition(needed <= height + 1, "Text overflow: \(s), \(needed) > \(height)")
    precondition(x >= 0 && y >= 0 && x+w <= W+1 && y+height <= H+1, "Text outside page")
    a.draw(with: NSRect(x: x, y: y, width: w, height: height),
           options: [.usesLineFragmentOrigin, .usesFontLeading])
}
func path(_ points: [(CGFloat, CGFloat)], color: NSColor = muted, width: CGFloat = 0.9) {
    ctx.saveGState(); ctx.setStrokeColor(color.cgColor); ctx.setLineWidth(width)
    ctx.setLineJoin(.round); ctx.setLineCap(.round)
    ctx.move(to: CGPoint(x: points[0].0, y: points[0].1))
    for p in points.dropFirst() { ctx.addLine(to: CGPoint(x: p.0, y: p.1)) }
    ctx.strokePath(); ctx.restoreGState()
}
func arrow(_ points: [(CGFloat, CGFloat)], color: NSColor = muted) {
    path(points, color: color)
    let a = points[points.count-2], b = points.last!
    let angle = atan2(b.1-a.1, b.0-a.0)
    let length: CGFloat = min(4.5, hypot(b.0-a.0, b.1-a.1)*0.4)
    path([(b.0-length*cos(angle-0.45), b.1-length*sin(angle-0.45)), b,
          (b.0-length*cos(angle+0.45), b.1-length*sin(angle+0.45))], color: color)
}
func section(_ letter: String, _ title: String, _ y: CGFloat, _ h: CGFloat,
             accent: NSColor, fill: String) {
    box(30, y, 535, h, fill: color(fill), stroke: accent, radius: 8, line: 0.7)
    let label = NSAttributedString(string: "(\(letter)) \(title)", attributes: [
        .font: NSFont.systemFont(ofSize: 9.5, weight: .semibold),
        .foregroundColor: accent
    ])
    let size = label.size()
    precondition(size.width <= h+12, "Vertical heading exceeds panel and half-gaps: \(title)")
    precondition(size.height < 20, "Vertical heading exceeds left margin")
    ctx.saveGState()
    ctx.translateBy(x: 18, y: y+h/2)
    ctx.rotate(by: -.pi/2)
    label.draw(at: NSPoint(x: -size.width/2, y: -size.height/2))
    ctx.restoreGState()
}

box(0, topTrim, W, exportHeight, fill: white, stroke: white, radius: 0)
// Centre the compact figure including its external, bottom-to-top headings.
ctx.translateBy(x: 8, y: 0)

// (a) Concise source cards preserve the accepted data content.
section("a", "Data", 85, 98, accent: blue, fill: "EFF6FC")
let dataCards: [(CGFloat, String, String, String)] = [
    (44, "Phenology", "European · all countries", "BBCH07 · 65 · 81 · 89"),
    (216, "Weather", "ERA5-Land daily", "0.1° grid"),
    (388, "Terrain", "Copernicus GLO-30 (~30 m)", "ERA5 grid geopotential")
]
for (x,title,l1,l2) in dataCards {
    box(x, 99, 163, 56, stroke: color("B9D0E4"))
    text(title, x+10, 105, 143, size: 11, weight: .semibold, color: blue)
    if x == 44 {
        text(l1, x+10, 121, 143, size: 9.3, height: 13)
        text(l2, x+10, 134, 143, size: 9.0, height: 12)
    } else {
        text(l1, x+10, 124, 143, size: 10, height: 15)
        text(l2, x+10, 138, 143, size: 10, height: 15)
    }
    arrow([(x+81.5,156),(x+81.5,163)], color: blue)
}
text("BBCH harmonization  →  quality control  →  site–year matching",
     44, 164, 507, size: 10.5, align: .center, height: 17)
arrow([(297.5,184),(297.5,195)])

// (b) Input correction is a separate factor from forcing response.
section("b", "Temperature", 199, 75, accent: ochre, fill: "FFF6E9")
box(72, 213, 195, 25, stroke: color("D7B887"))
box(328, 213, 195, 25, stroke: color("D7B887"))
text("Raw temperature", 80, 217, 179, size: 11, weight: .medium, color: ochre, align: .center)
text("DEM-corrected temperature", 336, 217, 179, size: 11, weight: .medium, color: ochre, align: .center)
// Real typographic subscripts, with elevations in metres throughout.
let equation = NSMutableAttributedString(string: "")
func math(_ s: String, sub: Bool = false, units: Bool = false) {
    equation.append(NSAttributedString(string: s, attributes: [
        .font: NSFont.systemFont(ofSize: sub ? 8 : (units ? 9.5 : 12)),
        .foregroundColor: ink, .baselineOffset: sub ? -3 : 0
    ]))
}
math("T"); math("adj", sub: true); math(" = T"); math("raw", sub: true)
math(" − 0.0065 × (z"); math("site", sub: true)
math(" − z"); math("grid", sub: true); math(")")
math("    T in °C; z in m", units: true)
precondition(equation.size().width < 507 && equation.size().height < 24)
equation.draw(at: NSPoint(x: (W-equation.size().width)/2, y: 247))
arrow([(297.5,275),(297.5,286)])

// (c) Factor-based design; each row crosses its function, ML and temperature options.
section("c", "Models", 290, 193 + modelExtraHeight, accent: purple, fill: "F5F0FA")
let tableX: CGFloat = 44, tableY: CGFloat = 304, rowH: CGFloat = 37
box(tableX, tableY, 507, 135, fill: .white, stroke: color("CFBEDF"))
box(377, tableY+1, 173, 133, fill: color("EDE3F6"), stroke: color("EDE3F6"), radius: 0)
let columnX: [CGFloat] = [52, 152, 297, 385, 451]
let columnWidths: [CGFloat] = [84, 129, 72, 50, 92]
let factorHeaders = ["Process", "Function", "Interaction", "ML", "T"]
for i in factorHeaders.indices {
    text(factorHeaders[i], columnX[i], tableY+6, columnWidths[i], weight: .semibold, color: purple)
}
path([(45,tableY+23),(550,tableY+23)], color: color("CFBEDF"), width: 0.6)
let factorRows = [
    ["Forcing", "Linear / beta", "—", "No / Yes", "Original /\nDEM-corrected"],
    ["Chilling +\nforcing", "F: linear / beta\nC: triangular / beta", "Sequential", "No / Yes", "Original /\nDEM-corrected"],
    ["Chilling +\nforcing", "F: linear / beta\nC: triangular / beta", "Parallel", "No / Yes", "Original /\nDEM-corrected"]
]
let structuresPerFamily = [2, 4, 4]
let catalogue = [
    ("Linear", "None", "—", "FL", "FL-ML"),
    ("Linear", "Piecewise linear", "Sequential", "CL-FL-S", "CL-FL-S-ML"),
    ("Linear", "Piecewise linear", "Parallel", "CL-FL-P", "CL-FL-P-ML"),
    ("Linear", "Beta", "Sequential", "CB-FL-S", "CB-FL-S-ML"),
    ("Linear", "Beta", "Parallel", "CB-FL-P", "CB-FL-P-ML"),
    ("Beta", "None", "—", "FB", "FB-ML"),
    ("Beta", "Piecewise linear", "Sequential", "CL-FB-S", "CL-FB-S-ML"),
    ("Beta", "Piecewise linear", "Parallel", "CL-FB-P", "CL-FB-P-ML"),
    ("Beta", "Beta", "Sequential", "CB-FB-S", "CB-FB-S-ML"),
    ("Beta", "Beta", "Parallel", "CB-FB-P", "CB-FB-P-ML")
]
let structureCount = catalogue.count
let configurationCount = structureCount * 2 * 2 // temperature inputs × residual-ML options
precondition(structureCount == 10 && configurationCount == 40)
precondition(structuresPerFamily.reduce(0, +) == structureCount && factorRows.count == structuresPerFamily.count)
precondition(Set(catalogue.map { $0.3 }).count == 10, "Duplicate process-model names")
precondition(Set(catalogue.map { $0.4 }).count == 10, "Duplicate residual-model names")
for row in catalogue {
    let suffix = row.2 == "Sequential" ? "-S" : "-P"
    precondition(row.1 == "None" ? row.2 == "—" && ["FL", "FB"].contains(row.3) : row.3.hasSuffix(suffix), "Interaction/name mismatch")
    precondition(row.4 == row.3 + "-ML", "Incorrect residual-ML suffix")
}
for (i, row) in factorRows.enumerated() {
    let y = tableY + 28 + CGFloat(i)*rowH
    for j in row.indices {
        text(row[j], columnX[j], y, columnWidths[j], size: 10, color: j >= 3 ? purple : ink, height: 31)
    }
    if i < factorRows.count-1 { path([(45,y+32),(550,y+32)], color: color("CFBEDF"), width: 0.4) }
}
text("FL · FB · CL-FL-S · CL-FL-P · CB-FL-S · CB-FL-P",
     44, 443, 507, size: 10, color: purple, align: .center, height: 15)
text("CL-FB-S · CL-FB-P · CB-FB-S · CB-FB-P    (add -ML for residual learning)",
     44, 458, 507, size: 10, color: purple, align: .center, height: 15)
let catalogueSummary = "\(structureCount) structures × 2 inputs × 2 ML options = \(configurationCount) per BBCH stage"
text(catalogueSummary,
     44, 467 + modelExtraHeight, 507, size: 10.5, weight: .semibold, color: purple, align: .center, height: 16)
arrow([(297.5,484 + modelExtraHeight),(297.5,495 + modelExtraHeight)])
ctx.saveGState()
ctx.translateBy(x: 0, y: modelExtraHeight)

// (d) A single directional link separates calibration and independent testing.
section("d", "Calibration and testing", 499, 145, accent: green, fill: "EFF8F3")
text("Random site split · stratified by clustered temperature zones",
     44, 509, 507, size: 10.5, align: .center, height: 17)
box(44, 533, 225, 77, stroke: color("99BFAF"), dash: true)
box(326, 533, 225, 77, stroke: color("99BFAF"), dash: true)
text("Calibration set · 80%", 56, 539, 201, size: 11, weight: .semibold, color: green)
text("Calibrate all process parameters", 56, 559, 201, size: 10)
text("Fit ML on out-of-fold residuals", 56, 574, 201, size: 10)
text("Tune within grouped inner folds", 56, 589, 201, size: 10)
text("Test set · 20%", 338, 539, 201, size: 11, weight: .semibold, color: green)
text("Apply locked process / hybrid models", 338, 559, 201, size: 10)
text("MAE · RMSE · Bias (days)", 338, 574, 201, size: 10)
text("Identical held-out sites for all models", 338, 589, 201, size: 10)
text("Lock", 275, 552, 45, size: 9.5, color: green, align: .center)
arrow([(272,573),(323,573)], color: green)
text("Keep each site intact · Additional spatial and warm-year holdouts",
     44, 622, 507, size: 10.5, align: .center, height: 17)
arrow([(297.5,645),(297.5,656)])

// (e) Paired temperature-treatment contrasts across terrain conditions.
section("e", "Terrain effects", 660, 129, accent: rose, fill: "FCF0F3")
text("Paired test errors · same sites, years and stages",
     44, 672, 507, size: 10.5, weight: .medium, color: rose, align: .center, height: 17)
box(44, 697, 225, 62, stroke: color("D6A5B2"))
box(326, 697, 225, 62, stroke: color("D6A5B2"))
text("Terrain descriptors", 56, 703, 201, size: 11, weight: .semibold, color: rose)
text("Site-to-grid elevation difference", 56, 724, 201, size: 10)
text("Elevation · slope · aspect · relief", 56, 738, 201, size: 10)
text("Temperature-correction benefit", 338, 703, 201, size: 11, weight: .semibold, color: rose)
text("MAE(RAW) − MAE(DEM)", 338, 724, 201, size: 10)
text("Compare without / with residual ML", 338, 738, 201, size: 10)
arrow([(272,728),(323,728)], color: rose)
text("Positive difference = improvement · Paired site-group uncertainty",
     44, 769, 507, size: 10, align: .center, height: 17)

ctx.restoreGState()
NSGraphicsContext.restoreGraphicsState()
ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
let bounds = page.bounds(for: .mediaBox)
precondition(abs(bounds.width-W)<0.01 && abs(bounds.height-exportHeight)<0.01, "Incorrect cropped page size")
let image = page.thumbnail(of: NSSize(width: W*3, height: exportHeight*3), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(
    to: URL(fileURLWithPath: "fig/workflow/workflow.png"))
let contents = (page.string ?? "").components(separatedBy: .whitespacesAndNewlines)
    .filter { !$0.isEmpty }.joined(separator: " ")
for term in catalogue.map({ $0.3 }) + factorHeaders + ["Sequential", "Parallel", "Original", "DEM-corrected", "No / Yes", "C: triangular / beta", "add -ML for residual learning", catalogueSummary, "European", "all countries", "BBCH07 · 65 · 81 · 89", "Calibration set", "Test set", "0.0065", "80%", "20%", "Random site split", "Terrain effects", "Terrain descriptors", "Temperature-correction benefit", "MAE(RAW) − MAE(DEM)", "Paired site-group uncertainty"] {
    precondition(contents.contains(term), "Missing PDF text: \(term)")
}
for absent in ["Grapevine phenology modelling", "Wergifosse", "Beta chilling:", "F forcing", "5 outer", "Γ", "24 configurations", "Climate-change impacts", "SSP2-4.5", "SSP5-8.5", "Future", "Hypothesis:"] {
    precondition(!contents.contains(absent), "Removed heading/footer remains: \(absent)")
}
precondition(contents.contains("clustered temperature zones"), "Missing temperature-zone stratification")
precondition(!contents.contains("stratified by country"), "Obsolete country stratification remains")
print("Exported vertically cropped vector PDF and PNG (595.28 × \(Int(exportHeight)) pt); five-factor table, ten structure names, terrain-effect comparisons and 40 configurations verified.")
