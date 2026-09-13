// Run from the repository root:
// swift -module-cache-path /tmp/grape-workflow-swift-cache src/phenology/draw_workflow.swift
// Completed manuscript workflow; exports selectable vector text to fig/workflow/.
import Foundation
import AppKit
import PDFKit

let directory = URL(fileURLWithPath: CommandLine.arguments[1])
let output = directory.appendingPathComponent("workflow.pdf")
let W: CGFloat = 595.2756, H: CGFloat = 841.8898 // Original A4 layout coordinates
let exportHeight: CGFloat = 740, topTrim: CGFloat = 73
let outputWidth: CGFloat = 180 * 72 / 25.4
let geometryScale = outputWidth/W
let outputHeight = exportHeight*geometryScale
var media = CGRect(x: 0, y: 0, width: outputWidth, height: outputHeight)
let ctx = CGContext(output as CFURL, mediaBox: &media, [
    kCGPDFContextTitle: "Grapevine phenology modelling workflow",
    kCGPDFContextSubject: "Completed grouped calibration, locked predictions and paired process/DEM/ML analyses"
] as CFDictionary)!
ctx.beginPDFPage(nil)
ctx.translateBy(x: 0, y: outputHeight)
ctx.scaleBy(x: geometryScale, y: -geometryScale)
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
          size: CGFloat = 8, weight: NSFont.Weight = .regular,
          color: NSColor = ink, align: NSTextAlignment = .left, height: CGFloat = 16) {
    let p = NSMutableParagraphStyle()
    p.alignment = align; p.lineSpacing = 1
    let a = NSAttributedString(string: s, attributes: [
        .font: NSFont(name: weight == .regular ? "Helvetica" : "Helvetica-Bold", size: size/geometryScale)!,
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
func section(_ letter: String, _ y: CGFloat, _ h: CGFloat,
             accent: NSColor, fill: String) {
    box(30, y, 535, h, fill: color(fill), stroke: accent, radius: 8, line: 0.7)
    let label = NSAttributedString(string: "(\(letter))", attributes: [
        .font: NSFont(name: "Helvetica-Bold", size: 9/geometryScale)!,
        .foregroundColor: accent
    ])
    let size = label.size()
    precondition(size.width < 22, "Panel label exceeds left margin")
    ctx.saveGState()
    ctx.translateBy(x: 18, y: y+h/2)
    label.draw(at: NSPoint(x: -size.width/2, y: -size.height/2))
    ctx.restoreGState()
}

box(0, topTrim, W, exportHeight, fill: white, stroke: white, radius: 0)
// Centre the compact figure including its horizontal external panel letters.
ctx.translateBy(x: 8, y: 0)

// (a) Matched modelling population, distinct from the phenology-only export.
section("a", 85, 88, accent: blue, fill: "EFF6FC")
let dataCards: [(CGFloat, String, String, String)] = [
    (44, "Phenology", "11 countries · 1951–2025", "BBCH07 · 65 · 81 · 89"),
    (216, "Weather", "ERA5-Land daily", "0.1° grid"),
    (388, "Terrain", "Copernicus GLO-30 (~30 m)", "ERA5 grid geopotential")
]
for (x,title,l1,l2) in dataCards {
    box(x, 96, 163, 49, stroke: color("B9D0E4"))
    text(title, x+9, 101, 145, size: 8, weight: .semibold, color: blue)
    text(l1, x+9, 116, 145, height: 13)
    text(l2, x+9, 129, 145, height: 13)
    arrow([(x+81.5,146),(x+81.5,153)], color: blue)
}
text("QC + weather / terrain matching: 74,618 observations · 3,169 sites",
     44, 155, 507, align: .center, height: 15)
arrow([(297.5,174),(297.5,182)])

// (b) Input correction is a separate factor from forcing response.
section("b", 185, 64, accent: ochre, fill: "FFF6E9")
box(72, 195, 195, 22, stroke: color("D7B887"))
box(328, 195, 195, 22, stroke: color("D7B887"))
text("RAW temperature", 80, 199, 179, weight: .medium, color: ochre, align: .center)
text("DEM-corrected temperature", 336, 199, 179, weight: .medium, color: ochre, align: .center)
// Real typographic subscripts, with elevations in metres throughout.
let equation = NSMutableAttributedString(string: "")
func math(_ s: String, sub: Bool = false, units: Bool = false) {
    equation.append(NSAttributedString(string: s, attributes: [
        .font: NSFont(name: "Helvetica", size: (sub ? 6 : 8)/geometryScale)!,
        .foregroundColor: ink, .baselineOffset: sub ? -2/geometryScale : 0
    ]))
}
math("T"); math("adj", sub: true); math(" = T"); math("raw", sub: true)
math(" − 0.0065 × (z"); math("site", sub: true)
math(" − z"); math("grid", sub: true); math(")")
math("    T in °C; z in m", units: true)
precondition(equation.size().width < 507 && equation.size().height < 24)
equation.draw(at: NSPoint(x: (W-equation.size().width)/2, y: 227))
arrow([(297.5,250),(297.5,258)])

// (c) Factor-based design; each row crosses its function, ML and temperature options.
section("c", 261, 166, accent: purple, fill: "F5F0FA")
text("Fixed temperature responses · calibrated accumulation thresholds",44,267,507,color:purple,align:.center)
let tableX: CGFloat = 44, tableY: CGFloat = 286, rowH: CGFloat = 26
box(tableX, tableY, 507, 101, fill: .white, stroke: color("CFBEDF"))
box(377, tableY+1, 173, 99, fill: color("EDE3F6"), stroke: color("EDE3F6"), radius: 0)
let columnX: [CGFloat] = [52, 152, 297, 385, 451]
let columnWidths: [CGFloat] = [84, 129, 72, 50, 92]
let factorHeaders = ["Process", "Function", "Interaction", "ML", "T"]
for i in factorHeaders.indices {
    text(factorHeaders[i], columnX[i], tableY+6, columnWidths[i], weight: .semibold, color: purple)
}
path([(45,tableY+23),(550,tableY+23)], color: color("CFBEDF"), width: 0.6)
let factorRows = [
    ["Forcing", "Linear / beta", "—", "No / Yes", "RAW / DEM"],
    ["Chilling +\nforcing", "F: linear / beta\nC: triangular / beta", "Sequential", "No / Yes", "RAW / DEM"],
    ["Chilling +\nforcing", "F: linear / beta\nC: triangular / beta", "Parallel", "No / Yes", "RAW / DEM"]
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
    let y = tableY + 24 + CGFloat(i)*rowH
    for j in row.indices {
        text(row[j], columnX[j], y, columnWidths[j], color: j >= 3 ? purple : ink, height: 25)
    }
    if i < factorRows.count-1 { path([(45,y+25),(550,y+25)], color: color("CFBEDF"), width: 0.4) }
}
text("FL · FB · CL-FL-S · CL-FL-P · CB-FL-S · CB-FL-P",
     44, 387, 507, color: purple, align: .center, height: 13)
text("CL-FB-S · CL-FB-P · CB-FB-S · CB-FB-P    (add -ML for residual learning)",
     44, 400, 507, color: purple, align: .center, height: 13)
let catalogueSummary = "\(structureCount) structures × 2 inputs × 2 ML options = \(configurationCount) per BBCH stage"
text(catalogueSummary,
     44, 412, 507, weight: .semibold, color: purple, align: .center, height: 13)
arrow([(297.5,428),(297.5,436)])

// (d) A single directional link separates calibration and independent testing.
section("d", 439, 188, accent: green, fill: "EFF8F3")
text("1991–2020 RAW monthly profiles · k-means · 5 environmental zones",
     44, 450, 507, align: .center, height: 15)
text("Random split within zones · keep grid / coordinate groups intact",
     44, 465, 507, align: .center, height: 15)
box(44, 487, 225, 115, stroke: color("99BFAF"), dash: true)
box(326, 487, 225, 115, stroke: color("99BFAF"), dash: true)
text("Calibration (~80%) · 2,534 sites", 53, 493, 207, weight: .semibold, color: green)
text("1,434 groups · 59,472 observations",53,508,207)
text("07 / 65 / 81: joint threshold fitting",53,527,207)
text("Raw attainment ≥99%",53,541,207)
text("89: equal-site weighted median",53,555,207)
text("TabM: out-of-fold process residuals",53,569,207)
text("4 grouped folds + 6 nested refits",53,583,207)
text("Test (~20%) · 635 sites",335,493,207,weight:.semibold,color:green)
text("357 groups · 15,146 observations",335,508,207)
text("Apply locked process / hybrid models",335,527,207)
text("Retain raw dates + attainment flags",335,541,207)
text("81 / 89: 4 November scoring cutoff",335,555,207)
text("No test labels in fitting or tuning",335,569,207)
text("Match finite scores for each contrast",335,583,207)
text("Lock",275,535,45,color:green,align:.center)
arrow([(272,555),(323,555)],color:green)
text("Same partitions for all models · stage sequence 07 / 65 / 81 / 89",
     44,609,507,align:.center,height:15)
arrow([(297.5,628),(297.5,636)])

// (e) Six completed Results analyses; no arrow implies a preliminary model selection.
section("e",639,162,accent:rose,fill:"FCF0F3")
text("Scoring errors · paired model and correction contrasts",44,649,507,
     weight:.medium,color:rose,align:.center,height:15)
let resultCards: [(String,String,String)] = [
    ("Process accuracy", "RAW errors", "Calibration / held-out test"),
    ("Structural contrasts", "21 RAW model pairs", "Forcing · chilling · interaction"),
    ("Spatial patterns", "CB-FL-S (RAW)", "Site errors and zones"),
    ("DEM: process models", "RAW − DEM MAE", "Terrain · zones · countries"),
    ("ML gains", "Process − hybrid MAE", "Baseline performance + zones"),
    ("DEM: hybrid models", "RAW − DEM MAE", "Compare with process models")
]
for (i,card) in resultCards.enumerated() {
    let x:CGFloat=44+CGFloat(i%3)*172, y:CGFloat=669+CGFloat(i/3)*51
    box(x,y,163,46,stroke:color("D6A5B2"))
    text(card.0,x+7,y+4,149,weight:.semibold,color:rose,height:13)
    text(card.1,x+7,y+18,149,height:13)
    text(card.2,x+7,y+31,149,height:13)
}
text("Paired gains: equal sites + stages · 2,000 original-group bootstrap draws",44,772,507,
     align:.center,height:13)
text("Positive MAE gain indicates improved accuracy",44,786,507,
     align:.center,height:13)
NSGraphicsContext.restoreGraphicsState()
ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
let bounds = page.bounds(for: .mediaBox)
precondition(abs(bounds.width-outputWidth)<0.01 && abs(bounds.height-outputHeight)<0.01, "Incorrect 180-mm cropped page size")
let image = page.thumbnail(of: NSSize(width: outputWidth*3, height: outputHeight*3), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(
    to: directory.appendingPathComponent("workflow.png"))
let contents = (page.string ?? "").components(separatedBy: .whitespacesAndNewlines)
    .filter { !$0.isEmpty }.joined(separator: " ")
for term in catalogue.map({ $0.3 }) + factorHeaders + ["Sequential", "Parallel", "RAW / DEM", "DEM-corrected", "No / Yes", "C: triangular / beta", "add -ML for residual learning", catalogueSummary, "11 countries", "BBCH07 · 65 · 81 · 89", "74,618", "3,169", "2,534", "635 sites", "1,434 groups", "357 groups", "0.0065", "80%", "20%", "Random split within zones", "1991–2020", "k-means", "4 November", "weighted median", "6 nested refits", "21 RAW model pairs", "Baseline performance + zones", "Compare with process models", "2,000 original-group"] {
    precondition(contents.contains(term), "Missing PDF text: \(term)")
}
for absent in ["Bias target", "Fig.", "Grapevine phenology modelling", "Wergifosse", "Beta chilling:", "F forcing", "5 outer", "Γ", "24 configurations", "Climate-change impacts", "SSP2-4.5", "SSP5-8.5", "Future", "Hypothesis:"] {
    precondition(!contents.contains(absent), "Removed heading/footer remains: \(absent)")
}
precondition(contents.contains("5 environmental zones"), "Missing environmental-zone stratification")
precondition(!contents.contains("stratified by country"), "Obsolete country stratification remains")
for letter in ["a", "b", "c", "d", "e"] {
    precondition(contents.contains("(\(letter))"), "Missing parenthesized panel label")
}
var extractedFonts = Set<String>(), extractedSizes = Set<Double>()
if let attributed = page.attributedString {
    attributed.enumerateAttribute(.font, in: NSRange(location: 0, length: attributed.length)) { value, _, _ in
        if let font = value as? NSFont {
            extractedFonts.insert(font.fontName)
            extractedSizes.insert((Double(font.pointSize)*100).rounded()/100)
            precondition(font.fontName.contains("Helvetica"), "Unexpected font: \(font.fontName)")
            precondition([CGFloat(6), 8, 9].contains(where: { abs(font.pointSize-$0)<0.05 }), "Unexpected PDF font size: \(font.pointSize)")
        }
    }
}
let typography: [String: Any] = [
    "page_width_pt": bounds.width, "page_height_pt": bounds.height,
    "width_mm": 180, "height_mm": bounds.height*25.4/72,
    "fonts": extractedFonts.sorted(), "font_sizes_pt": extractedSizes.sorted(),
    "ordinary_text_pt": 8, "panel_letters_pt": 9, "math_subscripts_pt": 6,
    "panel_labels": ["(a)", "(b)", "(c)", "(d)", "(e)"], "subplot_titles": false,
    "geometry_scale": geometryScale, "body_text_size_compensated_for_geometry_scale": true
]
try JSONSerialization.data(withJSONObject: typography, options: [.prettyPrinted, .sortedKeys]).write(
    to: directory.appendingPathComponent("workflow_typography.json"))
print("Exported 180-mm-wide vector PDF and PNG; Helvetica 8 pt body, 6 pt subscripts and 9 pt bold panel letters; five-factor table and all 40 configurations verified.")
