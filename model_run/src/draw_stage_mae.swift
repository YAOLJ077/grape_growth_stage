// Four calibrated-test panels, with shared scale and explicit model identities.
import Foundation
import AppKit
import PDFKit

let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let spec = try JSONSerialization.jsonObject(with: data) as! [String: Any]
let panels = spec["panels"] as! [[String: Any]]
let names = spec["model_order"] as! [String]
let upper = spec["y_max"] as! Double
let step = spec["y_tick_step"] as! Double
let folder = URL(fileURLWithPath: CommandLine.arguments[2])
let output = folder.appendingPathComponent("mae_by_stage_model.pdf")
let width: CGFloat = 640, height: CGFloat = 550
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
let ink = color(0x27333D), blue = color(0x326C9C)
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
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(media)
let headings = ["(a) BBCH07 · Budburst", "(b) BBCH65 · Flowering",
                "(c) BBCH81 · Veraison", "(d) BBCH89 · Maturity/harvest"]
for (p, panel) in panels.enumerated() {
    let plot = CGRect(x: 64+CGFloat(p%2)*294, y: 40+CGFloat(p/2)*250, width: 250, height: 168)
    label(headings[p], plot.minX, plot.minY-29, 13)
    for tick in stride(from: 0.0, through: upper, by: step) {
        let y = plot.maxY-CGFloat(tick/upper)*plot.height
        if tick > 0 { line(plot.minX, y, plot.maxX, y, color(0xE2E5E7), 0.5) }
        line(plot.minX-3, y, plot.minX, y, ink)
        label(String(format: "%.0f", tick), plot.minX-7, y-6, 11, 2)
    }
    let values = panel["values"] as! [Double]
    precondition(values.count == names.count)
    let spacing = plot.width/CGFloat(names.count)
    for (index, value) in values.enumerated() {
        precondition(value >= 0 && value <= upper)
        let x = plot.minX+(CGFloat(index)+0.5)*spacing
        let h = CGFloat(value/upper)*plot.height
        let rect = CGRect(x: x-spacing*0.35, y: plot.maxY-h, width: spacing*0.7, height: h)
        ctx.setFillColor(blue.cgColor); ctx.fill(rect)
        ctx.setStrokeColor(ink.cgColor); ctx.setLineWidth(0.35); ctx.stroke(rect)
        line(x, plot.maxY, x, plot.maxY+3, ink)
        ctx.saveGState()
        ctx.translateBy(x: x-3, y: plot.maxY+8); ctx.rotate(by: .pi/3)
        text(names[index], 10).draw(at: CGPoint(x: 0, y: 0))
        ctx.restoreGState()
    }
    line(plot.minX, plot.minY, plot.minX, plot.maxY, ink)
    line(plot.minX, plot.maxY, plot.maxX, plot.maxY, ink)
}
label(spec["x_axis"] as! String, width/2+15, 525, 15, 1)
let vertical = text(spec["y_axis"] as! String, 15)
ctx.saveGState(); ctx.translateBy(x: 12, y: 250); ctx.rotate(by: -.pi/2)
vertical.draw(at: CGPoint(x: -vertical.size().width/2, y: 0)); ctx.restoreGState()
NSGraphicsContext.restoreGraphicsState(); ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
for stage in ["07", "65", "81", "89"] { precondition((page.string ?? "").contains("BBCH"+stage)) }
for name in names { precondition((page.string ?? "").contains(name)) }
let preview = page.thumbnail(of: NSSize(width: width*300/72, height: height*300/72), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: preview.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent("mae_by_stage_model.png"))
print("Exported four stage panels and forty bars, with a shared zero-based MAE scale.")
