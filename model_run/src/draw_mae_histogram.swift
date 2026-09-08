// Native vector rendering, matching the repository's existing figure tools.
import Foundation
import AppKit
import PDFKit

let payload = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let spec = try JSONSerialization.jsonObject(with: payload) as! [String: Any]
let bins = spec["bins"] as! [[String: Any]]
let folder = URL(fileURLWithPath: CommandLine.arguments[2])
let output = folder.appendingPathComponent("mae_histogram.pdf")
let width: CGFloat = 432, height: CGFloat = 312
let plot = CGRect(x: 70, y: 16, width: 342, height: 228)
let low = bins.first!["left"] as! Double, high = bins.last!["right"] as! Double
let maximum = bins.map { $0["count"] as! Int }.max()!
let upper = Double(maximum + 1)
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
func label(_ value: String, x: CGFloat, y: CGFloat, size: CGFloat, align: Int = 1) {
    let text = NSAttributedString(string: value, attributes: [
        .font: NSFont.systemFont(ofSize: size), .foregroundColor: ink])
    let left = align == 1 ? x-text.size().width/2 : x-text.size().width
    precondition(left >= 0 && left+text.size().width <= width && y >= 0 && y+text.size().height <= height)
    text.draw(at: CGPoint(x: left, y: y))
}
func line(_ x1: CGFloat, _ y1: CGFloat, _ x2: CGFloat, _ y2: CGFloat, _ shade: NSColor, _ weight: CGFloat = 0.7) {
    ctx.setStrokeColor(shade.cgColor); ctx.setLineWidth(weight)
    ctx.move(to: CGPoint(x: x1, y: y1)); ctx.addLine(to: CGPoint(x: x2, y: y2)); ctx.strokePath()
}
func xpos(_ value: Double) -> CGFloat { plot.minX+CGFloat((value-low)/(high-low))*plot.width }
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(media)
for tick in 0...Int(upper) {
    let y = plot.maxY-CGFloat(Double(tick)/upper)*plot.height
    if tick > 0 { line(plot.minX, y, plot.maxX, y, color(0xE2E5E7), 0.5) }
    line(plot.minX-4, y, plot.minX, y, ink)
    label(String(tick), x: plot.minX-10, y: y-7, size: 12, align: 2)
}
for bin in bins {
    let left = xpos(bin["left"] as! Double), right = xpos(bin["right"] as! Double)
    let h = CGFloat(Double(bin["count"] as! Int)/upper)*plot.height
    let rectangle = CGRect(x: left, y: plot.maxY-h, width: right-left, height: h)
    ctx.setFillColor(blue.cgColor); ctx.fill(rectangle)
    ctx.setStrokeColor(NSColor.white.cgColor); ctx.setLineWidth(0.8); ctx.stroke(rectangle)
}
let strideSize = max(1, Int(ceil(Double(bins.count)/6)))
var ticks = Array(stride(from: 0, through: bins.count, by: strideSize))
if ticks.last != bins.count { ticks.append(bins.count) }
for index in ticks {
    let value = index == bins.count ? high : bins[index]["left"] as! Double
    let x = xpos(value)
    line(x, plot.maxY, x, plot.maxY+4, ink)
    label(String(format: "%.1f", value), x: x, y: plot.maxY+11, size: 12)
}
line(plot.minX, plot.minY, plot.minX, plot.maxY, ink)
line(plot.minX, plot.maxY, plot.maxX, plot.maxY, ink)
label(spec["x_axis"] as! String, x: plot.midX, y: 286, size: 15)
let vertical = NSAttributedString(string: spec["y_axis"] as! String, attributes: [
    .font: NSFont.systemFont(ofSize: 15), .foregroundColor: ink])
ctx.saveGState(); ctx.translateBy(x: 16, y: plot.midY); ctx.rotate(by: -.pi/2)
vertical.draw(at: CGPoint(x: -vertical.size().width/2, y: 0)); ctx.restoreGState()
NSGraphicsContext.restoreGraphicsState(); ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
for field in ["x_axis", "y_axis"] { precondition((page.string ?? "").contains(spec[field] as! String)) }
let preview = page.thumbnail(of: NSSize(width: width*300/72, height: height*300/72), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: preview.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent("mae_histogram.png"))
print("Exported one-page vector PDF and 300-dpi-sized PNG; no figure title.")
