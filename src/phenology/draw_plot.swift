// Run via: python3 src/phenology/plot_stage_counts.py
import Foundation
import AppKit
import PDFKit

let data = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
let rows = try JSONSerialization.jsonObject(with: data) as! [[String: Any]]
let folder = URL(fileURLWithPath: CommandLine.arguments[2])
let output = folder.appendingPathComponent("phen_data.pdf")
let width: CGFloat = 420, height: CGFloat = 350
let plot = CGRect(x: 78, y: 16, width: 328, height: 276)
let maximum = rows.map { $0["count"] as! Int }.max()!
let tickStep = pow(10, floor(log10(Double(maximum)))) / 2
let upper = ceil(Double(maximum)/tickStep) * tickStep
var media = CGRect(x: 0, y: 0, width: width, height: height)
let ctx = CGContext(output as CFURL, mediaBox: &media,
                    [kCGPDFContextTitle: "Phenology observation counts by BBCH stage"] as CFDictionary)!
ctx.beginPDFPage(nil)
ctx.translateBy(x: 0, y: height); ctx.scaleBy(x: 1, y: -1)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)
func color(_ value: UInt32) -> NSColor {
    NSColor(srgbRed: CGFloat((value>>16)&255)/255, green: CGFloat((value>>8)&255)/255,
            blue: CGFloat(value&255)/255, alpha: 1)
}
let ink = color(0x27333D), blue = color(0x326C9C)
func label(_ value: String, x: CGFloat, y: CGFloat, size: CGFloat, align: Int = 0) {
    let text = NSAttributedString(string: value, attributes: [
        .font: NSFont.systemFont(ofSize: size), .foregroundColor: ink])
    let textSize = text.size()
    let left = align == 0 ? x : align == 1 ? x-textSize.width/2 : x-textSize.width
    precondition(left >= 0 && left+textSize.width <= width && y >= 0 && y+textSize.height <= height,
                 "Text outside page: \(value)")
    text.draw(at: CGPoint(x: left, y: y))
}
func line(_ start: CGPoint, _ end: CGPoint, shade: NSColor, weight: CGFloat) {
    ctx.setStrokeColor(shade.cgColor); ctx.setLineWidth(weight)
    ctx.move(to: start); ctx.addLine(to: end); ctx.strokePath()
}
ctx.setFillColor(NSColor.white.cgColor); ctx.fill(media)
let formatter = NumberFormatter(); formatter.numberStyle = .decimal
for tick in stride(from: 0.0, through: upper, by: tickStep) {
    let y = plot.maxY-CGFloat(tick/upper)*plot.height
    if tick > 0 {
        line(CGPoint(x: plot.minX,y: y), CGPoint(x: plot.maxX,y: y), shade: color(0xE2E5E7), weight: 0.5)
    }
    line(CGPoint(x: plot.minX-4,y: y), CGPoint(x: plot.minX,y: y), shade: ink, weight: 0.6)
    label(formatter.string(from: NSNumber(value: Int(tick)))!, x: plot.minX-9, y: y-6, size: 11, align: 2)
}
let spacing = plot.width/CGFloat(rows.count)
let barWidth = spacing*0.52
for (index,row) in rows.enumerated() {
    let count = row["count"] as! Int
    let x = plot.minX+(CGFloat(index)+0.5)*spacing
    let h = CGFloat(Double(count)/upper)*plot.height
    precondition(h > 0 && h <= plot.height)
    ctx.setFillColor(blue.cgColor)
    ctx.fill(CGRect(x: x-barWidth/2, y: plot.maxY-h, width: barWidth, height: h))
    line(CGPoint(x: x,y: plot.maxY), CGPoint(x: x,y: plot.maxY+3), shade: ink, weight: 0.5)
    label(row["BBCH"] as! String, x: x, y: plot.maxY+7, size: 13, align: 1)
}
line(CGPoint(x: plot.minX,y: plot.minY), CGPoint(x: plot.minX,y: plot.maxY), shade: ink, weight: 0.7)
line(CGPoint(x: plot.minX,y: plot.maxY), CGPoint(x: plot.maxX,y: plot.maxY), shade: ink, weight: 0.7)
label("BBCH stage", x: plot.midX, y: 325, size: 15, align: 1)
let vertical = NSAttributedString(string: "Number of observations", attributes: [
    .font: NSFont.systemFont(ofSize: 15), .foregroundColor: ink])
ctx.saveGState(); ctx.translateBy(x: 13, y: plot.midY); ctx.rotate(by: -.pi/2)
vertical.draw(at: CGPoint(x: -vertical.size().width/2, y: 0))
ctx.restoreGState()
NSGraphicsContext.restoreGraphicsState(); ctx.endPDFPage(); ctx.closePDF()
let pdf = PDFDocument(url: output)!
precondition(pdf.pageCount == 1)
let page = pdf.page(at: 0)!
precondition(page.bounds(for: .mediaBox).size == media.size)
for axis in ["BBCH stage", "Number of observations"] {
    precondition((page.string ?? "").contains(axis), "Missing axis label")
}
let preview = page.thumbnail(of: NSSize(width: width*3, height: height*3), for: .mediaBox)
let bitmap = NSBitmapImageRep(data: preview.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: folder.appendingPathComponent("phen_data.png"))
print("Exported vector PDF and PNG with \(rows.count) bars; linear y-axis starts at zero.")
