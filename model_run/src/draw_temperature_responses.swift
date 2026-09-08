import Foundation
import AppKit
import PDFKit

let spec = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
let series = spec["series"] as! [[String: Any]]
let panels = spec["panels"] as! [[String]]
let folder = URL(fileURLWithPath: CommandLine.arguments[2])
let output = folder.appendingPathComponent("temperature_responses.pdf")
let width: CGFloat = 453, height: CGFloat = 420
var media = CGRect(x: 0, y: 0, width: width, height: height)
let ctx = CGContext(output as CFURL, mediaBox: &media, nil)!
ctx.beginPDFPage(nil)
ctx.translateBy(x: 0, y: height); ctx.scaleBy(x: 1, y: -1)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)
func color(_ h: UInt32) -> NSColor {
    NSColor(srgbRed: CGFloat((h>>16)&255)/255, green: CGFloat((h>>8)&255)/255,
            blue: CGFloat(h&255)/255, alpha: 1)
}
let ink = color(0x27333D), blue = color(0x326C9C), gold = color(0xB46B28), grid = color(0xE2E5E7)
func text(_ value: String, _ size: CGFloat) -> NSAttributedString {
    NSAttributedString(string: value, attributes: [.font: NSFont.systemFont(ofSize: size), .foregroundColor: ink])
}
func label(_ s: String, _ x: CGFloat, _ y: CGFloat, _ size: CGFloat, _ align: Int = 0) {
    let t = text(s, size)
    let left = align == 1 ? x-t.size().width/2 : align == 2 ? x-t.size().width : x
    precondition(left >= 0 && left+t.size().width <= width && y >= 0 && y+t.size().height <= height)
    t.draw(at: CGPoint(x: left, y: y))
}
func line(_ x1: CGFloat, _ y1: CGFloat, _ x2: CGFloat, _ y2: CGFloat, _ c: NSColor, _ weight: CGFloat = 0.7) {
    ctx.setStrokeColor(c.cgColor); ctx.setLineWidth(weight)
    ctx.move(to: CGPoint(x: x1, y: y1)); ctx.addLine(to: CGPoint(x: x2, y: y2)); ctx.strokePath()
}
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(media)
let headings = ["(a) Forcing", "(b) Chilling"]
let params = ["Relative to 25.4 °C", "−1.7 / 1.7 / 13.2 °C"]
let units = ["Relative forcing rate", "Chilling (units d⁻¹)"]
precondition(panels == [["FL", "FB"], ["CL", "CB"]])
for p in 0..<2 {
    let plot = CGRect(x: 64, y: 36+CGFloat(p)*190, width: 368, height: 142)
    let lower = -5.0, upper = p == 1 ? 20.0 : 45.0
    let ymax = p == 0 ? 2.0 : 1.08
    func x(_ t: Double) -> CGFloat { plot.minX+CGFloat((t-lower)/(upper-lower))*plot.width }
    func y(_ r: Double) -> CGFloat { plot.maxY-CGFloat(r/ymax)*plot.height }
    label(headings[p], plot.minX, plot.minY-28, 14)
    label(params[p], plot.maxX, plot.minY-27, 11, 2)
    let ticks = p == 0 ? [0.0, 0.5, 1.0, 1.5, 2.0] : [0.0, 0.5, 1.0]
    for tick in ticks {
        if tick > 0 { line(plot.minX, y(tick), plot.maxX, y(tick), grid, 0.5) }
        line(plot.minX-3, y(tick), plot.minX, y(tick), ink)
        label(String(format:"%.1f",tick), plot.minX-7, y(tick)-7, 11, 2)
    }
    let xticks = p == 1 ? [-5.0, 0, 5, 10, 15, 20] : [0.0, 10, 20, 30, 40]
    for tick in xticks {
        line(x(tick), plot.maxY, x(tick), plot.maxY+3, ink)
        label(String(format:"%.0f",tick), x(tick), plot.maxY+5, 11, 1)
    }
    let codes = panels[p]
    ctx.saveGState(); ctx.clip(to: plot)
    for code in codes {
        let item = series.first{($0["response"] as! String) == code}!
        let temperatures = item["temperature_c"] as! [Double], rates = item["display_rate"] as! [Double]
        let beta = code == "FB" || code == "CB"
        ctx.setStrokeColor((beta ? gold : blue).cgColor); ctx.setLineWidth(1.8)
        ctx.setLineDash(phase: 0, lengths: beta ? [6,3] : [])
        for (i, t) in temperatures.enumerated() {
            if i == 0 { ctx.move(to: CGPoint(x: x(t), y: y(rates[i]))) }
            else { ctx.addLine(to: CGPoint(x: x(t), y: y(rates[i]))) }
        }
        ctx.strokePath()
    }
    ctx.restoreGState()
    line(plot.minX, plot.minY, plot.minX, plot.maxY, ink)
    line(plot.minX, plot.maxY, plot.maxX, plot.maxY, ink)
    ctx.saveGState(); ctx.translateBy(x: 12, y: plot.midY); ctx.rotate(by: -.pi/2)
    let title = text(units[p], 12)
    title.draw(at: CGPoint(x: -title.size().width/2, y: 0)); ctx.restoreGState()
    let names = p == 0 ? ["Linear", "Beta"] : ["Triangular", "Beta"]
    let legendX: CGFloat = p == 0 ? 80 : 304
    for (i, name) in names.enumerated() {
        let ly = plot.minY+20+CGFloat(i)*25
        ctx.setLineDash(phase: 0, lengths: i == 1 ? [6,3] : [])
        line(legendX, ly, legendX+25, ly, i == 0 ? blue : gold, 1.8)
        ctx.setLineDash(phase: 0, lengths: [])
        label(name, legendX+33, ly-9, 15)
    }
}
label("Daily mean temperature (°C)", 248, 396, 14, 1)
NSGraphicsContext.restoreGraphicsState(); ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
for label in ["(a) Forcing", "(b) Chilling", "Relative forcing rate", "Linear", "Beta", "Triangular", "25.4"] {
    precondition((page.string ?? "").contains(label))
}
let preview = page.thumbnail(of: NSSize(width: width*300/72, height: height*300/72), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: preview.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent("temperature_responses.png"))
print("Exported paired forcing and chilling panels; forcing normalization is display-only.")
