import Foundation
import AppKit
import PDFKit

var documents: [[String: Any]] = []
for argument in CommandLine.arguments.dropFirst() {
    guard let document = PDFDocument(url: URL(fileURLWithPath: argument)) else {
        fatalError("Cannot read PDF: \(argument)")
    }
    var pages: [[String: Any]] = []
    for index in 0..<document.pageCount {
        let page = document.page(at: index)!
        var spans: [[String: Any]] = []
        if let content = page.attributedString {
            content.enumerateAttribute(.font, in: NSRange(location: 0, length: content.length)) { value, range, _ in
                guard let font = value as? NSFont else { return }
                let text = content.attributedSubstring(from: range).string.trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty {
                    let bounds = page.selection(for: range)?.bounds(for: page) ?? .zero
                    spans.append(["text": text, "font": font.fontName, "size": font.pointSize,
                                  "x": bounds.minX, "y": bounds.minY, "width": bounds.width, "height": bounds.height])
                }
            }
        }
        let box = page.bounds(for: .mediaBox)
        pages.append(["page": index+1, "width_pt": box.width, "height_pt": box.height,
                      "text": page.string ?? "", "spans": spans])
    }
    documents.append(["path": argument, "pages": pages])
}
let data = try JSONSerialization.data(withJSONObject: documents, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
