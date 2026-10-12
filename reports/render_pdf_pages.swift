// Renders each page of a PDF to <prefix>-<n>.png so the layout can be checked by eye.
// Usage: swift render_pdf_pages.swift report.pdf /path/to/prefix [max-pages]
import PDFKit
import AppKit
let args = CommandLine.arguments
let doc = PDFDocument(url: URL(fileURLWithPath: args[1]))!
let limit = args.count > 3 ? min(Int(args[3]) ?? doc.pageCount, doc.pageCount) : doc.pageCount
for i in 0..<limit {
  let page = doc.page(at: i)!
  let b = page.bounds(for: .mediaBox)
  let scale: CGFloat = 1.6
  let img = NSImage(size: NSSize(width: b.width*scale, height: b.height*scale))
  img.lockFocus()
  NSColor.white.set(); NSRect(origin: .zero, size: img.size).fill()
  let ctx = NSGraphicsContext.current!.cgContext
  ctx.scaleBy(x: scale, y: scale)
  page.draw(with: .mediaBox, to: ctx)
  img.unlockFocus()
  let rep = NSBitmapImageRep(data: img.tiffRepresentation!)!
  try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "\(args[2])-\(i+1).png"))
}
print(doc.pageCount)
