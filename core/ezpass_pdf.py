"""E-ZPass Service Receipt PDF — pixel-faithful reproduction of the branded receipt template."""

from decimal import Decimal
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas

PAGE_W, PAGE_H = letter          # 612 × 792 pts
M_L = 0.65 * inch               # left margin
M_R = 0.65 * inch               # right margin
CONTENT_W = PAGE_W - M_L - M_R  # usable width

# ── Palette ────────────────────────────────────────────────────────────────
NAVY      = colors.HexColor("#1a3a6b")
TEAL      = colors.HexColor("#3aaecc")
GOLD      = colors.HexColor("#c8a84b")
LIGHT_BG  = colors.HexColor("#f0f3f7")
BORDER    = colors.HexColor("#dde2ea")
DARK_GREY = colors.HexColor("#333333")
MID_GREY  = colors.HexColor("#555555")
MUTED     = colors.HexColor("#888888")
WHITE     = colors.white
BLUE_SUB  = colors.HexColor("#1a8fc7")


def _hline(pdf: Canvas, x1, y, x2, color=BORDER, width=0.6):
    pdf.setStrokeColor(color)
    pdf.setLineWidth(width)
    pdf.line(x1, y, x2, y)


def _vline(pdf: Canvas, x, y1, y2, color=BORDER, width=0.6):
    pdf.setStrokeColor(color)
    pdf.setLineWidth(width)
    pdf.line(x, y1, x, y2)


def _filled_circle(pdf: Canvas, cx, cy, r, fill_color=NAVY):
    pdf.setFillColor(fill_color)
    pdf.setStrokeColor(fill_color)
    pdf.circle(cx, cy, r, fill=1, stroke=0)


def _person_icon(pdf: Canvas, cx, cy, r=10):
    """Approximate person silhouette inside a filled navy circle."""
    _filled_circle(pdf, cx, cy, r + 3)
    pdf.setFillColor(WHITE)
    # head
    pdf.circle(cx, cy + 3, 4, fill=1, stroke=0)
    # body arc
    pdf.setFillColor(WHITE)
    pdf.ellipse(cx - 6, cy - 10, cx + 6, cy - 1, fill=1, stroke=0)


def _doc_icon(pdf: Canvas, cx, cy):
    _filled_circle(pdf, cx, cy, 13)
    pdf.setFillColor(WHITE)
    pdf.setLineWidth(0)
    # small document rectangle
    pdf.rect(cx - 5, cy - 7, 10, 14, fill=1, stroke=0)
    # fold corner
    pdf.setFillColor(NAVY)
    pdf.rect(cx + 1, cy + 4, 4, 3, fill=1, stroke=0)
    # lines on doc
    pdf.setFillColor(NAVY)
    for i in range(3):
        pdf.rect(cx - 4, cy - 5 + i * 4, 7, 1, fill=1, stroke=0)


def _cal_icon(pdf: Canvas, cx, cy):
    _filled_circle(pdf, cx, cy, 13)
    pdf.setFillColor(WHITE)
    # calendar box
    pdf.rect(cx - 7, cy - 7, 14, 13, fill=1, stroke=0)
    # top bar
    pdf.setFillColor(NAVY)
    pdf.rect(cx - 7, cy + 3, 14, 3, fill=1, stroke=0)
    # grid dots
    pdf.setFillColor(NAVY)
    for row in range(2):
        for col in range(3):
            pdf.circle(cx - 4 + col * 4, cy - 1 - row * 4, 1.2, fill=1, stroke=0)


def _arrow_right(pdf: Canvas, x, y, color=GOLD, size=9):
    """Draw a right-pointing filled chevron/arrow at (x, y)."""
    pdf.setFillColor(color)
    pdf.setStrokeColor(color)
    path = pdf.beginPath()
    path.moveTo(x, y + size)
    path.lineTo(x + size, y)
    path.lineTo(x, y - size)
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)


def _arrow_left(pdf: Canvas, x, y, color=TEAL, size=9):
    pdf.setFillColor(color)
    pdf.setStrokeColor(color)
    path = pdf.beginPath()
    path.moveTo(x + size, y + size)
    path.lineTo(x, y)
    path.lineTo(x + size, y - size)
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_ezpass_receipt_pdf(pdf: Canvas, tag):
    """
    Draw the E-ZPass Service Receipt onto *pdf* (a ReportLab canvas).
    Layout faithfully reproduces the branded receipt template image.
    """
    space = tag.space

    # Computed values
    inv_num = tag.invoice.invoice_number if tag.invoice else f"EZP-{tag.id:06d}"
    date_str = (tag.assigned_at.strftime("%b %d, %Y") if tag.assigned_at
                else timezone.now().strftime("%b %d, %Y"))
    total = tag.retail_price or Decimal("0.00")
    toll  = tag.toll_deposit  or Decimal("0.00")
    fee   = tag.convenience_fee or Decimal("0.00")

    cur_y = PAGE_H  # top of page

    # ════════════════════════════════════════════════════════════════
    # 1. HEADER  (white bg, bottom gold rule)
    # ════════════════════════════════════════════════════════════════
    hdr_h = 1.55 * inch
    hdr_bot_y = PAGE_H - hdr_h

    # White header background (page is white, no-op but explicit)
    pdf.setFillColor(WHITE)
    pdf.rect(0, hdr_bot_y, PAGE_W, hdr_h, fill=1, stroke=0)

    # ── E-ZPass X logo (teal + navy chevrons) ────────────────
    lx, ly = M_L, hdr_bot_y + (hdr_h / 2)
    # Teal left chevron
    pdf.setFillColor(TEAL)
    pdf.setStrokeColor(TEAL)
    tl = 28  # half-height of chevron
    tw = 22  # width of chevron
    path = pdf.beginPath()
    path.moveTo(lx + tw, ly + tl)
    path.lineTo(lx,       ly)
    path.lineTo(lx + tw, ly - tl)
    path.lineTo(lx + tw + 12, ly - tl)
    path.lineTo(lx + 12,  ly)
    path.lineTo(lx + tw + 12, ly + tl)
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)

    # Navy right chevron (overlapping)
    nl = 28; nw = 22
    nx = lx + tw - 2
    pdf.setFillColor(NAVY)
    path = pdf.beginPath()
    path.moveTo(nx + nw, ly + nl)
    path.lineTo(nx,       ly)
    path.lineTo(nx + nw, ly - nl)
    path.lineTo(nx + nw + 12, ly - nl)
    path.lineTo(nx + 12,  ly)
    path.lineTo(nx + nw + 12, ly + nl)
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)

    logo_right = lx + tw + nw + 14

    # ── Title text ──────────────────────────────────────────
    tx = logo_right + 10
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(tx, ly + 8, "E-ZPass Service Receipt")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(MUTED)
    pdf.drawString(tx, ly - 8, "Not an official E-ZPass document")

    # ── Swoosh decoration (top-right) ────────────────────────
    # Draw three curved-ish stripes approximated as wide arcs / bezier
    sw_x = PAGE_W - M_R - 1.8 * inch
    sw_y = hdr_bot_y + hdr_h - 10
    for i, (alpha, col_hex) in enumerate([(0.35, "#c8cbd4"), (0.25, "#a0a8b8"), (0.18, "#808898")]):
        pdf.setStrokeColor(colors.HexColor(col_hex))
        pdf.setLineWidth(7 - i * 1.5)
        pdf.setStrokeAlpha(alpha * 2)
        path = pdf.beginPath()
        path.moveTo(sw_x - i * 12, sw_y - i * 8)
        path.curveTo(
            sw_x + 0.5 * inch, sw_y - 20 - i * 6,
            sw_x + 1.0 * inch, sw_y - 50 - i * 6,
            PAGE_W - M_R + 10,  sw_y - 65 - i * 8
        )
        pdf.drawPath(path, fill=0, stroke=1)
    pdf.setStrokeAlpha(1)

    # ── Gold rule at bottom of header ────────────────────────
    pdf.setFillColor(GOLD)
    pdf.rect(0, hdr_bot_y, PAGE_W, 3, fill=1, stroke=0)

    cur_y = hdr_bot_y - 3

    # ════════════════════════════════════════════════════════════════
    # 2. MIDDLE SECTION  (info left | service desc right)
    # ════════════════════════════════════════════════════════════════
    left_col_w  = 2.35 * inch
    right_col_x = M_L + left_col_w
    right_col_w = PAGE_W - right_col_x - M_R
    amt_col_w   = 1.0 * inch

    # We estimate the height needed: 3 info rows + svc rows + total
    info_row_h = 0.7 * inch
    mid_h = (info_row_h * 3) + 0.15 * inch   # enough for 3 info rows

    mid_top_y = cur_y
    mid_bot_y = mid_top_y - mid_h - 0.5 * inch  # some breathing room for svc rows

    # ── Left column border ────────────────────────────────────
    _vline(pdf, M_L + left_col_w, mid_bot_y, mid_top_y)

    # ── Right column headers (Service Description | Amount) ──
    sh_y = mid_top_y - 0.28 * inch
    pdf.setFont("Helvetica-Bold", 8)
    pdf.setFillColor(NAVY)
    desc_x = right_col_x + 12
    pdf.drawString(desc_x, sh_y, "Service Description")
    amt_x = PAGE_W - M_R - amt_col_w
    pdf.drawRightString(PAGE_W - M_R - 6, sh_y, "Amount")

    # Thin line under column headers
    _hline(pdf, right_col_x, sh_y - 4, PAGE_W - M_R)

    # ── Vertical line between desc and amount cols ────────────
    _vline(pdf, PAGE_W - M_R - amt_col_w, mid_bot_y, sh_y - 4)

    # ── Service rows ──────────────────────────────────────────
    svc_y = sh_y - 18
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(DARK_GREY)
    pdf.drawString(desc_x, svc_y, f"E-ZPass On-The-Go Transponder")

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(MID_GREY)
    tag_detail = f"Tag #{tag.tag_number}"
    if tag.plate_number:
        tag_detail += f"  ·  Plate: {tag.plate_state or 'NY'} {tag.plate_number}"
    pdf.drawString(desc_x, svc_y - 12, tag_detail)

    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(DARK_GREY)
    pdf.drawRightString(PAGE_W - M_R - 6, svc_y, f"${toll:.2f}")

    if fee:
        svc_y2 = svc_y - 30
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColor(DARK_GREY)
        pdf.drawString(desc_x, svc_y2, "Authorized Retailer Processing & Convenience Fee")
        pdf.drawRightString(PAGE_W - M_R - 6, svc_y2, f"${fee:.2f}")

    # ── Thin line above Total ─────────────────────────────────
    total_line_y = mid_bot_y + 0.42 * inch
    _hline(pdf, right_col_x, total_line_y, PAGE_W - M_R)

    # ── Total row ─────────────────────────────────────────────
    total_y = total_line_y - 0.22 * inch
    pdf.setFont("Helvetica-Bold", 12)
    pdf.setFillColor(NAVY)
    # "Total" label
    total_label_x = PAGE_W - M_R - amt_col_w - 10
    pdf.drawRightString(total_label_x, total_y, "Total")
    # Gold vertical separator
    pdf.setFillColor(GOLD)
    pdf.rect(total_label_x + 4, total_y - 3, 3, 16, fill=1, stroke=0)
    # Amount
    pdf.setFillColor(NAVY)
    pdf.drawRightString(PAGE_W - M_R - 6, total_y, f"${total:.2f}")

    # ── Left info rows ────────────────────────────────────────
    info_data = [
        ("customer", tag.customer_name or "—", "Customer Name"),
        ("doc",      inv_num,                   "Invoice #"),
        ("cal",      date_str,                  "Date"),
    ]

    ir_y = mid_top_y - 0.15 * inch
    for kind, value, label in info_data:
        # circle icon
        icon_cx = M_L + 0.3 * inch
        icon_cy = ir_y - 0.22 * inch

        if kind == "customer":
            _person_icon(pdf, icon_cx, icon_cy)
        elif kind == "doc":
            _doc_icon(pdf, icon_cx, icon_cy)
        else:
            _cal_icon(pdf, icon_cx, icon_cy)

        # Label + value
        tx2 = M_L + 0.65 * inch
        pdf.setFont("Helvetica-Bold", 8.5)
        pdf.setFillColor(NAVY)
        pdf.drawString(tx2, icon_cy + 4, label)
        pdf.setFont("Helvetica", 8.5)
        pdf.setFillColor(DARK_GREY)
        pdf.drawString(tx2, icon_cy - 8, str(value)[:32])

        # Underline
        _hline(pdf, M_L + 4, ir_y - 0.52 * inch, M_L + left_col_w - 4)
        ir_y -= info_row_h

    mid_bot_y = min(total_line_y - 0.5 * inch, ir_y - 0.1 * inch)
    cur_y = mid_bot_y - 0.05 * inch

    # ════════════════════════════════════════════════════════════════
    # 3. OUR SERVICES RIBBON
    # ════════════════════════════════════════════════════════════════
    ribbon_h = 0.35 * inch
    pdf.setFillColor(NAVY)
    pdf.rect(0, cur_y - ribbon_h, PAGE_W, ribbon_h, fill=1, stroke=0)

    # Two gold arrows
    ax = M_L
    ay = cur_y - ribbon_h / 2
    for i in range(2):
        _arrow_right(pdf, ax + i * 12, ay, color=GOLD, size=7)

    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(WHITE)
    pdf.drawString(ax + 30, ay - 4, "OUR SERVICES")

    cur_y -= ribbon_h

    # ════════════════════════════════════════════════════════════════
    # 4. SERVICES + CONTACT ZONE
    # ════════════════════════════════════════════════════════════════
    szone_h = 2.9 * inch
    szone_top = cur_y
    szone_bot = cur_y - szone_h

    # Dashed vertical divider at 50%
    mid_x = M_L + CONTENT_W / 2
    pdf.setStrokeColor(BORDER)
    pdf.setLineWidth(1)
    pdf.setDash([4, 4])
    pdf.line(mid_x, szone_bot, mid_x, szone_top)
    pdf.setDash([])

    services = [
        ("plate",    "Plates, registrations, DMV services",   ""),
        ("shield",   "Xpress insurance, auto, taxi,",         "and business coverages"),
        ("car",      "Roadside assistance services",           ""),
        ("wheel",    "Defensive Driving Course",               "Save 10% on your insurance premium"),
    ]

    sy = szone_top - 0.28 * inch
    for svc_kind, sname, sdesc in services:
        # Circle icon
        icx = M_L + 0.33 * inch
        icy = sy - 0.1 * inch

        _filled_circle(pdf, icx, icy, 16, fill_color=WHITE)
        pdf.setStrokeColor(NAVY)
        pdf.setLineWidth(1.5)
        pdf.circle(icx, icy, 16, fill=0, stroke=1)

        # Icon inside circle
        pdf.setFillColor(NAVY)
        if svc_kind == "plate":
            # Simplified plate: rectangle
            pdf.setFillColor(NAVY)
            pdf.rect(icx - 9, icy - 5, 18, 10, fill=0, stroke=1)
            pdf.rect(icx - 7, icy - 3, 14, 6, fill=0, stroke=1)
        elif svc_kind == "shield":
            path = pdf.beginPath()
            path.moveTo(icx, icy + 10)
            path.lineTo(icx - 9, icy + 5)
            path.lineTo(icx - 9, icy - 3)
            path.curveTo(icx - 9, icy - 9, icx, icy - 12, icx, icy - 12)
            path.curveTo(icx, icy - 12, icx + 9, icy - 9, icx + 9, icy - 3)
            path.lineTo(icx + 9, icy + 5)
            path.close()
            pdf.setFillColor(NAVY)
            pdf.drawPath(path, fill=1, stroke=0)
        elif svc_kind == "car":
            # simplified car profile
            pdf.setFillColor(NAVY)
            pdf.rect(icx - 10, icy - 6, 20, 8, fill=1, stroke=0)
            pdf.circle(icx - 6, icy - 7, 3.5, fill=1, stroke=0)
            pdf.circle(icx + 6, icy - 7, 3.5, fill=1, stroke=0)
        else:  # wheel
            pdf.setStrokeColor(NAVY)
            pdf.setLineWidth(2)
            pdf.circle(icx, icy, 10, fill=0, stroke=1)
            pdf.circle(icx, icy, 3, fill=1, stroke=0)
            for angle_deg in [0, 90, 180, 270]:
                import math
                a = math.radians(angle_deg)
                pdf.line(icx + 3 * math.cos(a), icy + 3 * math.sin(a),
                         icx + 10 * math.cos(a), icy + 10 * math.sin(a))

        # Text
        text_x = M_L + 0.75 * inch
        bold_name = (svc_kind in ("plate", "wheel"))
        pdf.setFont("Helvetica-Bold" if bold_name else "Helvetica", 8.5)
        pdf.setFillColor(NAVY if bold_name else DARK_GREY)
        pdf.drawString(text_x, icy + 3, sname)
        if sdesc:
            pdf.setFont("Helvetica", 7.5)
            pdf.setFillColor(MID_GREY)
            pdf.drawString(text_x, icy - 9, sdesc)

        # Separator line between entries
        _hline(pdf, M_L + 4, sy - 0.58 * inch, mid_x - 8)
        sy -= 0.68 * inch

    # ── Right side: contact info ─────────────────────────────
    rx = mid_x + 14
    ry = szone_top - 0.25 * inch

    pdf.setFont("Helvetica-Bold", 14)
    pdf.setFillColor(NAVY)
    pdf.drawString(rx, ry, "Protect your vehicle.")
    pdf.drawString(rx, ry - 18, "Protect your business.")

    # Gold underline
    pdf.setFillColor(GOLD)
    pdf.rect(rx, ry - 26, 50, 2, fill=1, stroke=0)

    ry -= 38
    pdf.setFont("Helvetica-Bold", 11)
    pdf.setFillColor(BLUE_SUB)
    pdf.drawString(rx, ry, "Get more from")
    pdf.drawString(rx, ry - 14, "one trusted team.")

    ry -= 36

    # Phone
    _filled_circle(pdf, rx + 12, ry, 12, fill_color=NAVY)
    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(rx + 12, ry - 3, "P")
    pdf.setFont("Helvetica-Bold", 9.5)
    pdf.setFillColor(NAVY)
    pdf.drawString(rx + 28, ry - 3, "(914) 961-6666")

    ry -= 28

    # Location
    _filled_circle(pdf, rx + 12, ry, 12, fill_color=NAVY)
    pdf.setFillColor(WHITE)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawCentredString(rx + 12, ry - 3, "L")
    pdf.setFont("Helvetica", 8.5)
    pdf.setFillColor(NAVY)
    pdf.drawString(rx + 28, ry + 3, "Visit us: 800 Yonkers Ave,")
    pdf.drawString(rx + 28, ry - 9, "Yonkers, NY 10704")

    cur_y = szone_bot

    # ════════════════════════════════════════════════════════════════
    # 5. FOOTER
    # ════════════════════════════════════════════════════════════════
    ftr_h = 0.48 * inch
    pdf.setFillColor(LIGHT_BG)
    pdf.rect(0, cur_y - ftr_h, PAGE_W, ftr_h, fill=1, stroke=0)

    fy = cur_y - ftr_h / 2

    # Left teal arrows
    lax = M_L
    for i in range(2):
        _arrow_right(pdf, lax + i * 14, fy, color=TEAL, size=10)

    # Left separator bar
    pdf.setFillColor(TEAL)
    pdf.rect(lax + 32, fy - 10, 2, 20, fill=1, stroke=0)

    # Footer text
    pdf.setFont("Helvetica", 9.5)
    pdf.setFillColor(DARK_GREY)
    pdf.drawCentredString(PAGE_W / 2, fy - 4, "Call today for service, coverage, and savings.")

    # Right separator bar
    rax = PAGE_W - M_R - 34
    pdf.setFillColor(TEAL)
    pdf.rect(rax, fy - 10, 2, 20, fill=1, stroke=0)

    # Right teal arrows (pointing left)
    for i in range(2):
        _arrow_left(pdf, rax + 4 + i * 14, fy, color=TEAL, size=10)
