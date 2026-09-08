import Foundation
import AppKit
import PDFKit

let spec = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
let panels = spec["panels"] as! [[String: Any]]
let names = spec["model_order"] as! [String]
let upper = spec["y_max"] as! Double
let folder = URL(fileURLWithPath: CommandLine.arguments[2])
let output = folder.appendingPathComponent("calibration_test_mae.pdf")
let width: CGFloat = 720, height: CGFloat = 655
var media = CGRect(x: 0, y: 0, width: width, height: height)
let ctx = CGContext(output as CFURL, mediaBox: &media, nil)!
ctx.beginPDFPage(nil)
ctx.translateBy(x: 0, y: height); ctx.scaleBy(x: 1, y: -1)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)
func color(_ hex: UInt32) -> NSColor {
    NSColor(srgbRed: CGFloat((hex>>16)&255)/255, green: CGFloat((hex>>8)&255)/255,
            blue: CGFloat(hex&255)/255, alpha: 1)
}
let ink = color(0x27333D), blue = color(0x326C9C), gold = color(0xB46B28), grid = color(0xE2E5E7)
func text(_ value: String, _ size: CGFloat) -> NSAttributedString {
    NSAttributedString(string: value, attributes: [.font: NSFont.systemFont(ofSize: size), .foregroundColor: ink])
}
func label(_ value: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ align: Int = 0) {
    let t = text(value, size)
    let left = align == 0 ? x : align == 1 ? x-t.size().width/2 : x-t.size().width
    precondition(left >= 0 && left+t.size().width <= width && y >= 0 && y+t.size().height <= height)
    t.draw(at: CGPoint(x: left, y: y))
}
func line(_ x1: CGFloat, _ y1: CGFloat, _ x2: CGFloat, _ y2: CGFloat, _ shade: NSColor, _ weight: CGFloat = 0.7) {
    ctx.setStrokeColor(shade.cgColor); ctx.setLineWidth(weight)
    ctx.move(to: CGPoint(x: x1, y: y1)); ctx.addLine(to: CGPoint(x: x2, y: y2)); ctx.strokePath()
}
func bar(_ rect: CGRect, _ test: Bool) {
    ctx.setFillColor((test ? NSColor.white : blue).cgColor); ctx.fill(rect)
    ctx.setStrokeColor((test ? gold : blue).cgColor); ctx.setLineWidth(test ? 1.5 : 0.6); ctx.stroke(rect)
}
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(media)
bar(CGRect(x: 222, y: 12, width: 17, height: 13), false)
label("Calibration", 246, 8, 15)
bar(CGRect(x: 365, y: 12, width: 17, height: 13), true)
label("Test", 389, 8, 15)
label("\(names.count) of 10 models", 694, 10, 11, 2)
let headings = ["(a) BBCH07 · Budburst", "(b) BBCH65 · Flowering",
                "(c) BBCH81 · Veraison", "(d) BBCH89 · Maturity/harvest"]
var anyMissing = false
for (p, panel) in panels.enumerated() {
    let plot = CGRect(x: 68+CGFloat(p%2)*346, y: 91+CGFloat(p/2)*282, width: 280, height: 186)
    label(headings[p], plot.minX, plot.minY-43, 14)
    let nc = panel["calibration_n"] as! Int, nt = panel["test_n"] as! Int
    label("Observations: \(nc) calibration / \(nt) test", plot.minX, plot.minY-23, 10)
    for tick in stride(from: 0.0, through: upper, by: spec["y_tick_step"] as! Double) {
        let y = plot.maxY-CGFloat(tick/upper)*plot.height
        if tick > 0 { line(plot.minX, y, plot.maxX, y, grid, 0.5) }
        line(plot.minX-3, y, plot.minX, y, ink)
        label(String(format: "%.0f", tick), plot.minX-7, y-7, 11, 2)
    }
    let spacing = plot.width/CGFloat(names.count), bw = spacing*0.33
    for (j, partition) in ["calibration", "test"].enumerated() {
        let values = panel[partition] as! [Double]
        let missing = panel[partition+"_missing"] as! [Int]
        precondition(values.count == names.count && missing.count == names.count)
        for (i, value) in values.enumerated() {
            precondition(value >= 0 && value <= upper)
            let x = plot.minX+(CGFloat(i)+0.5)*spacing+(j == 0 ? -bw*0.56 : bw*0.56)
            let h = CGFloat(value/upper)*plot.height
            bar(CGRect(x: x-bw/2, y: plot.maxY-h, width: bw, height: h), j == 1)
            if missing[i] > 0 {
                anyMissing = true
                label("†\(missing[i])", x, plot.maxY-h-15, 10, 1)
            }
        }
    }
    for (i, name) in names.enumerated() {
        let x = plot.minX+(CGFloat(i)+0.5)*spacing
        line(x, plot.maxY, x, plot.maxY+3, ink)
        ctx.saveGState(); ctx.translateBy(x: x-6, y: plot.maxY+8); ctx.rotate(by: .pi/4)
        text(name, 11).draw(at: CGPoint(x: 0, y: 0)); ctx.restoreGState()
    }
    line(plot.minX, plot.minY, plot.minX, plot.maxY, ink)
    line(plot.minX, plot.maxY, plot.maxX, plot.maxY, ink)
}
let vertical = text("Site-balanced MAE (days)", 15)
ctx.saveGState(); ctx.translateBy(x: 12, y: 315); ctx.rotate(by: -.pi/2)
vertical.draw(at: CGPoint(x: -vertical.size().width/2, y: 0)); ctx.restoreGState()
label("Model", width/2, 614, 15, 1)
if anyMissing {
    label("† Number of unattained observations; MAE uses attained events only.", width/2, 640, 10, 1)
}
NSGraphicsContext.restoreGraphicsState(); ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
for value in ["Calibration", "Test", "BBCH07", "BBCH65", "BBCH81", "BBCH89"] + names {
    precondition((page.string ?? "").contains(value))
}
let preview = page.thumbnail(of: NSSize(width: width*300/72, height: height*300/72), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: preview.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent("calibration_test_mae.png"))
print("Exported calibration/test MAE panels for \(names.count) models.")
