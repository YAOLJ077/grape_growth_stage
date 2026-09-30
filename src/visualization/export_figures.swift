// Render 300 dpi previews of the PDFs scaled by pypdf without changing their font mappings.
import Foundation
import AppKit
import PDFKit
let jobs = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath:CommandLine.arguments[1]))) as! [[String:String]]
for job in jobs {
 try autoreleasepool {
  let output=URL(fileURLWithPath:job["output"]!)
  let result=CGPDFDocument(output as CFURL)!, resultPage=result.page(at:1)!
  let box=resultPage.getBoxRect(.mediaBox), width=box.width, height=box.height
  let pixelsWide=Int((width*300/72).rounded()), pixelsHigh=Int((height*300/72).rounded())
  let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:pixelsWide,pixelsHigh:pixelsHigh,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
  let graphics=NSGraphicsContext(bitmapImageRep:rep)!, raster=graphics.cgContext
  raster.setFillColor(NSColor.white.cgColor);raster.fill(CGRect(x:0,y:0,width:pixelsWide,height:pixelsHigh))
  raster.scaleBy(x:CGFloat(pixelsWide)/width,y:CGFloat(pixelsHigh)/height);raster.drawPDFPage(resultPage)
  // Set print dimensions after drawing so AppKit does not apply a second scale.
  rep.size=NSSize(width:width,height:height)
  try rep.representation(using:.png,properties:[:])!.write(to:output.deletingPathExtension().appendingPathExtension("png"))
  // Independent PDFKit preview catches clipped or double-scaled bitmap exports.
  let document=PDFDocument(url:output)!
  let reference=document.page(at:0)!.thumbnail(of:NSSize(width:pixelsWide,height:pixelsHigh),for:.mediaBox)
  let referenceRep=NSBitmapImageRep(data:reference.tiffRepresentation!)!
  try referenceRep.representation(using:.png,properties:[:])!.write(to:
      output.deletingPathExtension().appendingPathExtension("reference.png"))
  print("Exported \(job["id"]!): \(width/72) inches, \(pixelsWide) px at 300 dpi")
 }
}
