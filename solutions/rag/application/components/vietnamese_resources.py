"""
Vietnamese Lexicons, Taxonomies and NLP Resources for AIP Enterprise RAG Solution.
Standardized across 9 key Vietnamese enterprise domains (Groups A - I):
- Group A: Conversational & Chat Shorthands (ko, dc, ntn, vs, mk, mn, chx, etc.)
- Group B: Administrative & Legal (NĐ, NQ, QĐ, CT, TT, VBQPPL, TTHC, etc.)
- Group C: Human Resources, Payroll & Appraisal (NLĐ, NSDLĐ, HĐLĐ, BHXH, TNLĐ-BNN, KPI, C&B, etc.)
- Group D: Accounting, Finance, Banking & Tax (BCTC, BCĐKT, TSCĐ, GTGT, VAT, TNDN, HĐĐT, MST, etc.)
- Group E: Corporate Governance & Operations (DN, TNHH, CTCP, GPKD, ĐKKD, HĐQT, SLA, CRM, ERP, etc.)
- Group F: Information Technology, Data & AI (CNTT, CSDL, API, LLM, RAG, NLP, CI/CD, RBAC, etc.)
- Group G: Health Insurance & Clinical Medical (KCB, CSKCB, BHYT, DSPHSK, HSBA, ICD, etc.)
- Group H: Education & Training (GDĐT, ĐH, CĐ, CTĐT, ĐGNL, NCKH, GPA, etc.)
- Group I: Procurement, Bidding, Projects & Construction (HSMT, HSDT, KHLCNT, CĐT, PCCC, ATLĐ, etc.)

Includes:
- EnterpriseTerm standard metadata schema (DoD >= 98% compliant)
- Automatic generation of unaccented lookup keys (normalized_aliases)
- Ambiguity policy handling (context_aware, keep_original, direct)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, List, Optional, Set
import unicodedata


@dataclass
class EnterpriseTerm:
    """Standardized enterprise term metadata schema for AIP RAG taxonomy."""

    term_id: str
    canonical: str
    aliases: List[str]
    normalized_aliases: List[str] = field(default_factory=list)
    domain: List[str] = field(default_factory=list)
    term_type: str = "abbreviation"  # "abbreviation" | "compound_phrase" | "chat_shorthand" | "technical"
    expansion_policy: str = "direct"  # "direct" | "context_aware" | "keep_original"
    source: str = "verified_domain_glossary"
    verified: bool = False
    priority: int = 100


def strip_accents(text: str) -> str:
    """
    Strips Vietnamese diacritics/accents to ASCII equivalent.
    E.g. 'bảo hiểm xã hội' -> 'bao hiem xa hoi', 'nghị định' -> 'nghi dinh'.
    """
    if not text:
        return ""
    res = text.replace("đ", "d").replace("Đ", "D")
    nfd = unicodedata.normalize("NFD", res)
    unaccented = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", unaccented).lower().strip()


# ==============================================================================
# ENTERPRISE TERMS CATALOG: GROUPS A THROUGH I
# ==============================================================================
ENTERPRISE_TERMS_CATALOG: List[EnterpriseTerm] = [
    # --------------------------------------------------------------------------
    # Nhóm A — Viết tắt thông dụng trong câu hỏi (Chat Shorthand)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="CHAT_001", canonical="không",
        aliases=["ko", "k", "khum", "hok", "hông"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=80
    ),
    EnterpriseTerm(
        term_id="CHAT_002", canonical="được",
        aliases=["dc", "đc"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CHAT_003", canonical="như thế nào",
        aliases=["ntn"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=95
    ),
    EnterpriseTerm(
        term_id="CHAT_004", canonical="gì",
        aliases=["j"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=80
    ),
    EnterpriseTerm(
        term_id="CHAT_005", canonical="với",
        aliases=["vs"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="CHAT_006", canonical="mình",
        aliases=["mk"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=80
    ),
    EnterpriseTerm(
        term_id="CHAT_007", canonical="mọi người",
        aliases=["mn"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CHAT_008", canonical="rồi",
        aliases=["roi"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CHAT_009", canonical="chưa",
        aliases=["chx"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CHAT_010", canonical="nữa",
        aliases=["nx"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=80
    ),
    EnterpriseTerm(
        term_id="CHAT_011", canonical="inbox",
        aliases=["ib"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="CHAT_012", canonical="phản hồi",
        aliases=["rep"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="CHAT_013", canonical="quản trị viên",
        aliases=["ad"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=80
    ),
    EnterpriseTerm(
        term_id="CHAT_014", canonical="hồ sơ",
        aliases=["hs"],
        domain=["conversational", "administration"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CHAT_015", canonical="em",
        aliases=["e"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=80
    ),
    EnterpriseTerm(
        term_id="CHAT_016", canonical="giúp",
        aliases=["giup"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="direct",
        source="vietnamese_chat_corpus", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CHAT_017", canonical="bạn",
        aliases=["bn", "b"],
        domain=["conversational"], term_type="chat_shorthand", expansion_policy="context_aware",
        source="vietnamese_chat_corpus", verified=True, priority=80
    ),

    # --------------------------------------------------------------------------
    # Nhóm B — Hành chính và pháp luật (National Legal Database & Circulars)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="LEG_001", canonical="Nghị định",
        aliases=["NĐ", "ND"],
        domain=["legal", "administration"], term_type="abbreviation", expansion_policy="direct",
        source="vbpl.moj.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_002", canonical="Nghị quyết",
        aliases=["NQ"],
        domain=["legal", "administration"], term_type="abbreviation", expansion_policy="direct",
        source="vbpl.moj.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_003", canonical="Quyết định",
        aliases=["QĐ", "QD"],
        domain=["legal", "administration"], term_type="abbreviation", expansion_policy="direct",
        source="vbpl.moj.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_004", canonical="Chỉ thị",
        aliases=["CT"],
        domain=["legal", "administration"], term_type="abbreviation", expansion_policy="context_aware",
        source="vbpl.moj.gov.vn", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="LEG_005", canonical="Thông tư",
        aliases=["TT"],
        domain=["legal", "administration"], term_type="abbreviation", expansion_policy="context_aware",
        source="vbpl.moj.gov.vn", verified=True, priority=95
    ),
    EnterpriseTerm(
        term_id="LEG_006", canonical="Nghị quyết liên tịch",
        aliases=["NQLT"],
        domain=["legal", "administration"], term_type="abbreviation", expansion_policy="direct",
        source="vbpl.moj.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_007", canonical="Thông tư liên tịch",
        aliases=["TTLT"],
        domain=["legal", "administration"], term_type="abbreviation", expansion_policy="direct",
        source="vbpl.moj.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_008", canonical="Chính phủ",
        aliases=["CP"],
        domain=["legal", "government"], term_type="abbreviation", expansion_policy="context_aware",
        source="chinhphu.vn", verified=True, priority=95
    ),
    EnterpriseTerm(
        term_id="LEG_009", canonical="Thủ tướng Chính phủ",
        aliases=["TTg"],
        domain=["legal", "government"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_010", canonical="Văn bản quy phạm pháp luật",
        aliases=["VBQPPL"],
        domain=["legal"], term_type="abbreviation", expansion_policy="direct",
        source="vbpl.moj.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_011", canonical="Thủ tục hành chính",
        aliases=["TTHC"],
        domain=["administration"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_012", canonical="Cải cách hành chính",
        aliases=["CCHC"],
        domain=["administration"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_013", canonical="Quản lý nhà nước",
        aliases=["QLNN"],
        domain=["administration"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_014", canonical="Cơ quan nhà nước",
        aliases=["CQNN"],
        domain=["administration"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_015", canonical="Đơn vị sự nghiệp công lập",
        aliases=["ĐVSNCL", "DVSNCL"],
        domain=["administration"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_016", canonical="Cán bộ, công chức",
        aliases=["CBCC"],
        domain=["administration", "hr"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_017", canonical="Cán bộ, công chức, viên chức",
        aliases=["CBCCVC"],
        domain=["administration", "hr"], term_type="abbreviation", expansion_policy="direct",
        source="chinhphu.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_018", canonical="Viên chức",
        aliases=["VC"],
        domain=["administration", "hr"], term_type="abbreviation", expansion_policy="context_aware",
        source="chinhphu.vn", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="LEG_019", canonical="Căn cước công dân",
        aliases=["CCCD"],
        domain=["legal", "identification"], term_type="abbreviation", expansion_policy="direct",
        source="citizen_identity_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_020", canonical="Chứng minh nhân dân",
        aliases=["CMND"],
        domain=["legal", "identification"], term_type="abbreviation", expansion_policy="direct",
        source="citizen_identity_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_021", canonical="Ủy ban nhân dân",
        aliases=["UBND"],
        domain=["legal", "government"], term_type="abbreviation", expansion_policy="direct",
        source="local_government_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="LEG_022", canonical="Hội đồng nhân dân",
        aliases=["HĐND", "HDND"],
        domain=["legal", "government"], term_type="abbreviation", expansion_policy="direct",
        source="local_government_law", verified=True, priority=100
    ),

    # --------------------------------------------------------------------------
    # Nhóm C — Nhân sự, tiền lương và đánh giá công việc (HR & Labor Law)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="HR_001", canonical="Nhân sự",
        aliases=["NS"],
        domain=["hr"], term_type="abbreviation", expansion_policy="context_aware",
        source="enterprise_internal_hr", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="HR_002", canonical="Năng suất lao động",
        aliases=["NSLĐ", "NSLD"],
        domain=["hr", "operations"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_internal_hr", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_003", canonical="Người lao động",
        aliases=["NLĐ", "NLD"],
        domain=["hr", "labor_law"], term_type="abbreviation", expansion_policy="direct",
        source="labor_code_2019", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_004", canonical="Người sử dụng lao động",
        aliases=["NSDLĐ", "NSDLD"],
        domain=["hr", "labor_law"], term_type="abbreviation", expansion_policy="direct",
        source="labor_code_2019", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_005", canonical="Hợp đồng lao động",
        aliases=["HĐLĐ", "HDLD"],
        domain=["hr", "labor_law"], term_type="abbreviation", expansion_policy="direct",
        source="labor_code_2019", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_006", canonical="Hợp đồng làm việc",
        aliases=["HĐLV", "HDLV"],
        domain=["hr", "public_service"], term_type="abbreviation", expansion_policy="direct",
        source="law_on_cadres_civil_servants", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_007", canonical="Hợp đồng thử việc",
        aliases=["HĐTV", "HDTV"],
        domain=["hr", "labor_law"], term_type="abbreviation", expansion_policy="context_aware",
        source="enterprise_internal_hr", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="HR_008", canonical="Bảo hiểm xã hội",
        aliases=["BHXH"],
        domain=["insurance", "labor_law", "hr"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_009", canonical="Bảo hiểm y tế",
        aliases=["BHYT"],
        domain=["insurance", "hr"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_010", canonical="Bảo hiểm thất nghiệp",
        aliases=["BHTN"],
        domain=["insurance", "labor_law"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_011", canonical="Tai nạn lao động",
        aliases=["TNLĐ", "TNLD"],
        domain=["insurance", "labor_safety"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_012", canonical="Bệnh nghề nghiệp",
        aliases=["BNN"],
        domain=["insurance", "occupational_health"], term_type="abbreviation", expansion_policy="context_aware",
        source="baohiemxahoi.gov.vn", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="HR_013", canonical="Tai nạn lao động, bệnh nghề nghiệp",
        aliases=["TNLĐ-BNN", "TNLD-BNN"],
        domain=["insurance", "labor_safety"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_014", canonical="Chỉ số đánh giá hiệu quả công việc (KPI)",
        aliases=["KPI"],
        domain=["hr", "performance"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_performance_management", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_015", canonical="Mục tiêu và kết quả then chốt (OKR)",
        aliases=["OKR"],
        domain=["hr", "strategy"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_performance_management", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_016", canonical="Bản mô tả công việc (Job Description)",
        aliases=["JD"],
        domain=["hr", "recruitment"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_internal_hr", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_017", canonical="Hồ sơ ứng tuyển / Sơ yếu lý lịch",
        aliases=["CV"],
        domain=["hr", "recruitment"], term_type="abbreviation", expansion_policy="context_aware",
        source="enterprise_internal_hr", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="HR_018", canonical="Hành chính nhân sự",
        aliases=["HCNS"],
        domain=["hr", "administration"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_internal_hr", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_019", canonical="Chế độ đãi ngộ, tiền lương và phúc lợi (C&B)",
        aliases=["C&B", "CB"],
        domain=["hr", "payroll"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_internal_hr", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_020", canonical="Làm thêm giờ (Overtime)",
        aliases=["OT"],
        domain=["hr", "payroll"], term_type="abbreviation", expansion_policy="direct",
        source="labor_code_2019", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_021", canonical="Thuế thu nhập cá nhân (PIT)",
        aliases=["PIT"],
        domain=["tax", "payroll"], term_type="abbreviation", expansion_policy="direct",
        source="general_department_of_taxation", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_022", canonical="Thu nhập cá nhân",
        aliases=["TNCN"],
        domain=["tax", "payroll"], term_type="abbreviation", expansion_policy="direct",
        source="general_department_of_taxation", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="HR_023", canonical="Lao động",
        aliases=["LĐ", "LD"],
        domain=["hr", "labor_law"], term_type="abbreviation", expansion_policy="context_aware",
        source="labor_code_2019", verified=True, priority=85
    ),

    # --------------------------------------------------------------------------
    # Nhóm D — Kế toán, tài chính, ngân hàng và thuế (Tax & Accounting)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="ACC_001", canonical="Kế toán",
        aliases=["KT"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="context_aware",
        source="accounting_standards", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="ACC_002", canonical="Báo cáo tài chính",
        aliases=["BCTC"],
        domain=["accounting", "finance"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_003", canonical="Bảng cân đối kế toán",
        aliases=["BCĐKT", "BCDKT"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_004", canonical="Kết quả kinh doanh",
        aliases=["KQKD"],
        domain=["accounting", "finance"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_005", canonical="Lưu chuyển tiền tệ",
        aliases=["LCTT"],
        domain=["accounting", "finance"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_006", canonical="Tài sản cố định",
        aliases=["TSCĐ", "TSCD"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_007", canonical="Công cụ, dụng cụ",
        aliases=["CCDC"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_008", canonical="Hàng tồn kho",
        aliases=["HTK"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_009", canonical="Chi phí",
        aliases=["CP"],
        domain=["accounting", "finance"], term_type="abbreviation", expansion_policy="context_aware",
        source="vas_standards", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="ACC_010", canonical="Doanh thu",
        aliases=["DT"],
        domain=["accounting", "finance"], term_type="abbreviation", expansion_policy="context_aware",
        source="vas_standards", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="ACC_011", canonical="Lợi nhuận",
        aliases=["LN"],
        domain=["accounting", "finance"], term_type="abbreviation", expansion_policy="context_aware",
        source="vas_standards", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="ACC_012", canonical="Giá vốn hàng bán",
        aliases=["GVHB"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_013", canonical="Giá trị gia tăng",
        aliases=["GTGT"],
        domain=["tax", "accounting"], term_type="abbreviation", expansion_policy="direct",
        source="tax_regulations", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_014", canonical="Thuế giá trị gia tăng (VAT)",
        aliases=["VAT"],
        domain=["tax", "accounting"], term_type="abbreviation", expansion_policy="direct",
        source="tax_regulations", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_015", canonical="Thu nhập doanh nghiệp",
        aliases=["TNDN"],
        domain=["tax", "accounting"], term_type="abbreviation", expansion_policy="direct",
        source="tax_regulations", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_016", canonical="Tiêu thụ đặc biệt",
        aliases=["TTĐB", "TTDB"],
        domain=["tax"], term_type="abbreviation", expansion_policy="direct",
        source="tax_regulations", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_017", canonical="Ngân sách nhà nước",
        aliases=["NSNN"],
        domain=["finance", "government"], term_type="abbreviation", expansion_policy="direct",
        source="state_budget_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_018", canonical="Ngân hàng Nhà nước Việt Nam",
        aliases=["NHNN"],
        domain=["banking"], term_type="abbreviation", expansion_policy="direct",
        source="sbv.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_019", canonical="Ngân hàng thương mại",
        aliases=["NHTM"],
        domain=["banking"], term_type="abbreviation", expansion_policy="direct",
        source="sbv.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_020", canonical="Tài khoản",
        aliases=["TK"],
        domain=["banking", "accounting"], term_type="abbreviation", expansion_policy="context_aware",
        source="banking_accounting", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="ACC_021", canonical="Ủy nhiệm chi",
        aliases=["UNC"],
        domain=["banking"], term_type="abbreviation", expansion_policy="direct",
        source="banking_regulations", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_022", canonical="Ủy nhiệm thu",
        aliases=["UNT"],
        domain=["banking"], term_type="abbreviation", expansion_policy="direct",
        source="banking_regulations", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_023", canonical="Hóa đơn điện tử",
        aliases=["HĐĐT", "HDDT"],
        domain=["tax", "accounting"], term_type="abbreviation", expansion_policy="direct",
        source="decree_123_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_024", canonical="Mã số thuế",
        aliases=["MST"],
        domain=["tax", "accounting"], term_type="abbreviation", expansion_policy="direct",
        source="tax_administration_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_025", canonical="Chế độ kế toán",
        aliases=["CĐKT", "CDKT"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_026", canonical="Vốn chủ sở hữu",
        aliases=["VCSH"],
        domain=["accounting", "finance"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_027", canonical="Nợ phải trả",
        aliases=["NPT"],
        domain=["accounting"], term_type="abbreviation", expansion_policy="direct",
        source="vas_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_028", canonical="Tỷ suất sinh lời trên tài sản (ROA)",
        aliases=["ROA"],
        domain=["finance"], term_type="abbreviation", expansion_policy="direct",
        source="financial_analysis", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_029", canonical="Tỷ suất sinh lời trên vốn chủ sở hữu (ROE)",
        aliases=["ROE"],
        domain=["finance"], term_type="abbreviation", expansion_policy="direct",
        source="financial_analysis", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="ACC_030", canonical="Tỷ suất hoàn vốn đầu tư (ROI)",
        aliases=["ROI"],
        domain=["finance"], term_type="abbreviation", expansion_policy="direct",
        source="financial_analysis", verified=True, priority=100
    ),

    # --------------------------------------------------------------------------
    # Nhóm E — Doanh nghiệp và vận hành (Corporate & Operations)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="CORP_001", canonical="Doanh nghiệp",
        aliases=["DN"],
        domain=["corporate"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=95
    ),
    EnterpriseTerm(
        term_id="CORP_002", canonical="Doanh nghiệp nhà nước",
        aliases=["DNNN"],
        domain=["corporate"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_003", canonical="Doanh nghiệp tư nhân",
        aliases=["DNTN"],
        domain=["corporate"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_004", canonical="Trách nhiệm hữu hạn",
        aliases=["TNHH"],
        domain=["corporate"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_005", canonical="Cổ phần hóa",
        aliases=["CPH"],
        domain=["corporate"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_006", canonical="Công ty cổ phần",
        aliases=["CTCP"],
        domain=["corporate"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_007", canonical="Giấy phép kinh doanh",
        aliases=["GPKD"],
        domain=["corporate", "legal"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_008", canonical="Đăng ký kinh doanh",
        aliases=["ĐKKD", "DKKD"],
        domain=["corporate", "legal"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_009", canonical="Đăng ký doanh nghiệp",
        aliases=["ĐKDN", "DKDN"],
        domain=["corporate", "legal"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_010", canonical="Giám đốc",
        aliases=["GĐ", "GD"],
        domain=["corporate", "governance"], term_type="abbreviation", expansion_policy="context_aware",
        source="corporate_governance", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CORP_011", canonical="Tổng giám đốc",
        aliases=["TGĐ", "TGD"],
        domain=["corporate", "governance"], term_type="abbreviation", expansion_policy="direct",
        source="corporate_governance", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_012", canonical="Ban giám đốc",
        aliases=["BGĐ", "BGD"],
        domain=["corporate", "governance"], term_type="abbreviation", expansion_policy="direct",
        source="corporate_governance", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_013", canonical="Hội đồng quản trị",
        aliases=["HĐQT", "HDQT"],
        domain=["corporate", "governance"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_014", canonical="Hội đồng thành viên",
        aliases=["HĐTV", "HDTV"],
        domain=["corporate", "governance"], term_type="abbreviation", expansion_policy="context_aware",
        source="enterprise_law_2020", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CORP_015", canonical="Ban kiểm soát",
        aliases=["BKS"],
        domain=["corporate", "governance"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_law_2020", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_016", canonical="Sản xuất kinh doanh",
        aliases=["SXKD"],
        domain=["operations"], term_type="abbreviation", expansion_policy="direct",
        source="operations_management", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_017", canonical="Quản lý chất lượng",
        aliases=["QLCL"],
        domain=["operations", "quality"], term_type="abbreviation", expansion_policy="direct",
        source="iso_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_018", canonical="Quản trị rủi ro",
        aliases=["QTRR"],
        domain=["governance", "operations"], term_type="abbreviation", expansion_policy="direct",
        source="risk_management", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_019", canonical="Chăm sóc khách hàng",
        aliases=["CSKH"],
        domain=["customer_service"], term_type="abbreviation", expansion_policy="direct",
        source="customer_support", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_020", canonical="Khách hàng",
        aliases=["KH"],
        domain=["sales", "crm"], term_type="abbreviation", expansion_policy="context_aware",
        source="enterprise_operations", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="CORP_021", canonical="Nhà cung cấp",
        aliases=["NCC"],
        domain=["supply_chain"], term_type="abbreviation", expansion_policy="direct",
        source="procurement_supply_chain", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_022", canonical="Đơn đặt hàng (Purchase Order)",
        aliases=["PO"],
        domain=["procurement"], term_type="abbreviation", expansion_policy="direct",
        source="procurement_supply_chain", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_023", canonical="Yêu cầu mua hàng (Purchase Requisition)",
        aliases=["PR"],
        domain=["procurement"], term_type="abbreviation", expansion_policy="context_aware",
        source="procurement_supply_chain", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="CORP_024", canonical="Cam kết mức độ dịch vụ (SLA)",
        aliases=["SLA"],
        domain=["operations", "it"], term_type="abbreviation", expansion_policy="direct",
        source="service_management", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_025", canonical="Doanh nghiệp với doanh nghiệp (B2B)",
        aliases=["B2B"],
        domain=["commerce"], term_type="abbreviation", expansion_policy="direct",
        source="e_commerce", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_026", canonical="Doanh nghiệp với người tiêu dùng (B2C)",
        aliases=["B2C"],
        domain=["commerce"], term_type="abbreviation", expansion_policy="direct",
        source="e_commerce", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_027", canonical="Hệ thống quản lý quan hệ khách hàng (CRM)",
        aliases=["CRM"],
        domain=["it", "sales"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_systems", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_028", canonical="Hệ thống hoạch định nguồn lực doanh nghiệp (ERP)",
        aliases=["ERP"],
        domain=["it", "operations"], term_type="abbreviation", expansion_policy="direct",
        source="enterprise_systems", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="CORP_029", canonical="Quản lý chuỗi cung ứng (SCM)",
        aliases=["SCM"],
        domain=["supply_chain"], term_type="abbreviation", expansion_policy="direct",
        source="supply_chain_management", verified=True, priority=100
    ),

    # --------------------------------------------------------------------------
    # Nhóm F — Công nghệ thông tin, dữ liệu và AI (IT, Data & Engineering)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="TECH_001", canonical="Công nghệ thông tin",
        aliases=["CNTT", "IT"],
        domain=["technology"], term_type="abbreviation", expansion_policy="direct",
        source="moit.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_002", canonical="Hệ thống thông tin",
        aliases=["HTTT"],
        domain=["technology"], term_type="abbreviation", expansion_policy="direct",
        source="moit.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_003", canonical="Cơ sở dữ liệu",
        aliases=["CSDL", "DB"],
        domain=["data"], term_type="abbreviation", expansion_policy="direct",
        source="data_engineering", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_004", canonical="Giao diện lập trình ứng dụng (API)",
        aliases=["API"],
        domain=["software"], term_type="technical", expansion_policy="keep_original",
        source="software_engineering", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_005", canonical="Mô hình ngôn ngữ lớn (LLM)",
        aliases=["LLM"],
        domain=["ai"], term_type="technical", expansion_policy="keep_original",
        source="ai_research", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_006", canonical="Retrieval-Augmented Generation (RAG)",
        aliases=["RAG"],
        domain=["ai"], term_type="technical", expansion_policy="keep_original",
        source="ai_research", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_007", canonical="Xử lý ngôn ngữ tự nhiên (NLP)",
        aliases=["NLP"],
        domain=["ai"], term_type="technical", expansion_policy="direct",
        source="ai_research", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_008", canonical="Nhận dạng ký tự quang học (OCR)",
        aliases=["OCR"],
        domain=["ai"], term_type="technical", expansion_policy="direct",
        source="computer_vision", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_009", canonical="Trí tuệ nhân tạo (AI)",
        aliases=["AI"],
        domain=["ai"], term_type="technical", expansion_policy="keep_original",
        source="ai_research", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_010", canonical="Học máy (Machine Learning)",
        aliases=["ML"],
        domain=["ai"], term_type="technical", expansion_policy="direct",
        source="ai_research", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_011", canonical="Kiểm soát truy cập dựa trên vai trò (RBAC)",
        aliases=["RBAC"],
        domain=["security"], term_type="technical", expansion_policy="direct",
        source="security_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_012", canonical="Đăng nhập một lần (SSO)",
        aliases=["SSO"],
        domain=["security"], term_type="technical", expansion_policy="direct",
        source="security_standards", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_013", canonical="Thông tin nhận dạng cá nhân (PII)",
        aliases=["PII"],
        domain=["security", "privacy"], term_type="technical", expansion_policy="direct",
        source="iso_27001", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="TECH_014", canonical="Cơ sở dữ liệu vector (Vector Database)",
        aliases=["VDB"],
        domain=["ai", "database"], term_type="technical", expansion_policy="context_aware",
        source="rag_architecture", verified=True, priority=90
    ),

    # --------------------------------------------------------------------------
    # Nhóm G — Bảo hiểm và nghiệp vụ khám chữa bệnh (Healthcare & Insurance)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="MED_001", canonical="Khám bệnh, chữa bệnh",
        aliases=["KCB"],
        domain=["healthcare", "insurance"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="MED_002", canonical="Cơ sở khám bệnh, chữa bệnh",
        aliases=["CSKCB"],
        domain=["healthcare", "insurance"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="MED_003", canonical="Dưỡng sức, phục hồi sức khỏe",
        aliases=["DSPHSK"],
        domain=["insurance"], term_type="abbreviation", expansion_policy="direct",
        source="baohiemxahoi.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="MED_004", canonical="Hồ sơ bệnh án",
        aliases=["HSBA"],
        domain=["healthcare"], term_type="abbreviation", expansion_policy="direct",
        source="moh.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="MED_005", canonical="Bệnh nhân",
        aliases=["BN"],
        domain=["healthcare"], term_type="abbreviation", expansion_policy="context_aware",
        source="moh.gov.vn", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="MED_006", canonical="Bác sĩ",
        aliases=["BS"],
        domain=["healthcare"], term_type="abbreviation", expansion_policy="context_aware",
        source="moh.gov.vn", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="MED_007", canonical="Xét nghiệm",
        aliases=["XN"],
        domain=["healthcare"], term_type="abbreviation", expansion_policy="context_aware",
        source="moh.gov.vn", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="MED_008", canonical="Cận lâm sàng",
        aliases=["CLS"],
        domain=["healthcare"], term_type="abbreviation", expansion_policy="direct",
        source="moh.gov.vn", verified=True, priority=95
    ),
    EnterpriseTerm(
        term_id="MED_009", canonical="Lâm sàng",
        aliases=["LS"],
        domain=["healthcare"], term_type="abbreviation", expansion_policy="context_aware",
        source="moh.gov.vn", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="MED_010", canonical="Bộ Y tế",
        aliases=["BYT"],
        domain=["government", "healthcare"], term_type="abbreviation", expansion_policy="direct",
        source="moh.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="MED_011", canonical="Sở Y tế",
        aliases=["SYT"],
        domain=["government", "healthcare"], term_type="abbreviation", expansion_policy="direct",
        source="moh.gov.vn", verified=True, priority=100
    ),

    # --------------------------------------------------------------------------
    # Nhóm H — Giáo dục và đào tạo (Education & Training)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="EDU_001", canonical="Giáo dục và đào tạo",
        aliases=["GDĐT", "GDDT"],
        domain=["education"], term_type="abbreviation", expansion_policy="direct",
        source="moet.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="EDU_002", canonical="Giáo dục phổ thông",
        aliases=["GDPT"],
        domain=["education"], term_type="abbreviation", expansion_policy="direct",
        source="moet.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="EDU_003", canonical="Giáo dục thường xuyên",
        aliases=["GDTX"],
        domain=["education"], term_type="abbreviation", expansion_policy="direct",
        source="moet.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="EDU_004", canonical="Đại học",
        aliases=["ĐH", "DH"],
        domain=["education"], term_type="abbreviation", expansion_policy="context_aware",
        source="moet.gov.vn", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="EDU_005", canonical="Cao đẳng",
        aliases=["CĐ", "CD"],
        domain=["education"], term_type="abbreviation", expansion_policy="context_aware",
        source="moet.gov.vn", verified=True, priority=90
    ),
    EnterpriseTerm(
        term_id="EDU_006", canonical="Giảng viên",
        aliases=["GV"],
        domain=["education"], term_type="abbreviation", expansion_policy="context_aware",
        source="moet.gov.vn", verified=True, priority=85
    ),
    EnterpriseTerm(
        term_id="EDU_007", canonical="Sinh viên",
        aliases=["SV"],
        domain=["education"], term_type="abbreviation", expansion_policy="direct",
        source="moet.gov.vn", verified=True, priority=95
    ),
    EnterpriseTerm(
        term_id="EDU_008", canonical="Chương trình đào tạo",
        aliases=["CTĐT", "CTDT"],
        domain=["education"], term_type="abbreviation", expansion_policy="direct",
        source="moet.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="EDU_009", canonical="Đánh giá năng lực",
        aliases=["ĐGNL", "DGNL"],
        domain=["education"], term_type="abbreviation", expansion_policy="direct",
        source="moet.gov.vn", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="EDU_010", canonical="Nghiên cứu khoa học",
        aliases=["NCKH"],
        domain=["education", "science"], term_type="abbreviation", expansion_policy="direct",
        source="moet.gov.vn", verified=True, priority=100
    ),

    # --------------------------------------------------------------------------
    # Nhóm I — Mua sắm, đấu thầu, dự án và xây dựng (Procurement & Construction)
    # --------------------------------------------------------------------------
    EnterpriseTerm(
        term_id="PROC_001", canonical="Hồ sơ mời thầu",
        aliases=["HSMT"],
        domain=["procurement", "bidding"], term_type="abbreviation", expansion_policy="direct",
        source="bidding_law_2023", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_002", canonical="Hồ sơ dự thầu",
        aliases=["HSDT"],
        domain=["procurement", "bidding"], term_type="abbreviation", expansion_policy="direct",
        source="bidding_law_2023", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_003", canonical="Hồ sơ yêu cầu",
        aliases=["HSYC"],
        domain=["procurement", "bidding"], term_type="abbreviation", expansion_policy="direct",
        source="bidding_law_2023", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_004", canonical="Hồ sơ đề xuất",
        aliases=["HSĐX", "HSDX"],
        domain=["procurement", "bidding"], term_type="abbreviation", expansion_policy="direct",
        source="bidding_law_2023", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_005", canonical="Hồ sơ mời thầu qua mạng",
        aliases=["E-HSMT"],
        domain=["procurement", "bidding"], term_type="abbreviation", expansion_policy="direct",
        source="national_bidding_system", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_006", canonical="Hồ sơ dự thầu qua mạng",
        aliases=["E-HSDT"],
        domain=["procurement", "bidding"], term_type="abbreviation", expansion_policy="direct",
        source="national_bidding_system", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_007", canonical="Kế hoạch lựa chọn nhà thầu",
        aliases=["KHLCNT"],
        domain=["procurement", "bidding"], term_type="abbreviation", expansion_policy="direct",
        source="bidding_law_2023", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_008", canonical="Chủ đầu tư",
        aliases=["CĐT", "CDT"],
        domain=["construction", "project"], term_type="abbreviation", expansion_policy="direct",
        source="construction_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_009", canonical="Tư vấn giám sát",
        aliases=["TVGS"],
        domain=["construction", "project"], term_type="abbreviation", expansion_policy="direct",
        source="construction_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_010", canonical="Tư vấn thiết kế",
        aliases=["TVTK"],
        domain=["construction", "project"], term_type="abbreviation", expansion_policy="direct",
        source="construction_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_011", canonical="Phòng cháy, chữa cháy",
        aliases=["PCCC"],
        domain=["safety", "construction"], term_type="abbreviation", expansion_policy="direct",
        source="fire_safety_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_012", canonical="An toàn lao động",
        aliases=["ATLĐ", "ATLD"],
        domain=["safety", "labor"], term_type="abbreviation", expansion_policy="direct",
        source="labor_safety_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_013", canonical="Quản lý dự án",
        aliases=["QLDA"],
        domain=["project"], term_type="abbreviation", expansion_policy="direct",
        source="construction_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_014", canonical="Giải phóng mặt bằng",
        aliases=["GPMB"],
        domain=["construction", "land"], term_type="abbreviation", expansion_policy="direct",
        source="land_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_015", canonical="Thiết kế kỹ thuật",
        aliases=["TKKT"],
        domain=["construction"], term_type="abbreviation", expansion_policy="direct",
        source="construction_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_016", canonical="Bản vẽ thi công",
        aliases=["BVTC"],
        domain=["construction"], term_type="abbreviation", expansion_policy="direct",
        source="construction_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_017", canonical="Tổng mức đầu tư",
        aliases=["TMĐT", "TMDT"],
        domain=["construction", "finance"], term_type="abbreviation", expansion_policy="direct",
        source="construction_law", verified=True, priority=100
    ),
    EnterpriseTerm(
        term_id="PROC_018", canonical="Nhà thầu",
        aliases=["NT"],
        domain=["construction", "procurement"], term_type="abbreviation", expansion_policy="context_aware",
        source="bidding_law_2023", verified=True, priority=85
    ),
]


# ==============================================================================
# DYNAMIC DICTIONARY COMPILERS (AUTOMATIC UNACCENTED KEY GENERATION)
# ==============================================================================

# 1. Enterprise Acronyms (Expansion Map)
ENTERPRISE_ACRONYMS: Dict[str, str] = {}

# 2. Acronym Casing Map (Regex Casing Normalization to official uppercase)
ACRONYM_CASING_MAP: Dict[str, str] = {}

# 3. Conversational Chat Shorthand Map
CHAT_SHORTHAND_MAP: Dict[str, str] = {}

# 4. Diacritics Compound Phrase Map (Auto-generated from catalog canonicals + rich lexicons)
DIACRITICS_PHRASE_MAP: Dict[str, str] = {}

# Populate catalog terms with automatic unaccented normalized_aliases
for term in ENTERPRISE_TERMS_CATALOG:
    # 1. Compute unaccented normalized aliases
    norm_canonical = strip_accents(term.canonical)
    if norm_canonical not in term.normalized_aliases:
        term.normalized_aliases.append(norm_canonical)

    for alias in term.aliases:
        norm_alias = strip_accents(alias)
        if norm_alias not in term.normalized_aliases:
            term.normalized_aliases.append(norm_alias)

    # 2. Populate Enterprise Acronyms
    if term.term_type in ("abbreviation", "technical"):
        primary_alias = term.aliases[0]
        for alias in term.aliases:
            ENTERPRISE_ACRONYMS[alias] = term.canonical
            # Casing normalization - map all lowercase/unaccented aliases to the PRIMARY official casing
            low_alias = alias.lower()
            unacc_alias = strip_accents(alias)
            ACRONYM_CASING_MAP[low_alias] = primary_alias
            ACRONYM_CASING_MAP[unacc_alias] = primary_alias

    # 3. Populate Chat Shorthand Map
    if term.term_type == "chat_shorthand":
        for alias in term.aliases:
            CHAT_SHORTHAND_MAP[alias.lower()] = term.canonical
            CHAT_SHORTHAND_MAP[strip_accents(alias)] = term.canonical

    # 4. Auto-generate Diacritics Phrase Map entry
    if len(norm_canonical.split()) >= 2:
        canonical_target = term.canonical
        if not re.search(r'\([A-Z0-9_\-\&/]+\)', canonical_target) and not any(w.isupper() and len(w) > 1 for w in canonical_target.split()):
            canonical_target = canonical_target.lower()
        DIACRITICS_PHRASE_MAP[norm_canonical] = canonical_target


# ==============================================================================
# ADDITIONAL RICH COMPOUND PHRASES (Administrative, Legal & Corporate)
# ==============================================================================
ADDITIONAL_PHRASES: Dict[str, str] = {
    # Hướng dẫn, Quy trình, Thủ tục
    "huong dan su dung": "hướng dẫn sử dụng",
    "huong dan lam": "hướng dẫn làm",
    "huong dan": "hướng dẫn",
    "huong dan tra cuu": "hướng dẫn tra cứu",
    "tra cuu": "tra cứu",
    "truc tuyen": "trực tuyến",
    "cach phat hanh": "cách phát hành",
    "phat hanh hoa don": "phát hành hóa đơn",
    "phat hanh": "phát hành",
    "kiem toan": "kiểm toán",
    "dieu le to chuc": "điều lệ tổ chức",
    "dieu le": "điều lệ",
    "hoat dong": "hoạt động",
    "kham chua benh": "khám chữa bệnh",
    "kham benh": "khám bệnh",
    "chua benh": "chữa bệnh",
    "dang ky kinh doanh": "đăng ký kinh doanh",
    "dang ky": "đăng ký",
    "cap gpkd": "cấp GPKD",
    "cap moi": "cấp mới",
    "hop dong thu viec": "hợp đồng thử việc",
    "che do nghi thai san va tien thuong tet": "chế độ nghỉ thai sản và tiền thưởng tết",
    "che do nghi thai san": "chế độ nghỉ thai sản",
    "che do thai san": "chế độ thai sản",
    "che do nghi": "chế độ nghỉ",
    "che do": "chế độ",
    "duoc huong": "được hưởng",
    "cho minh hoi": "cho mình hỏi",
    "cho mk hoi": "cho mình hỏi",
    "nhan duoc": "nhận được",
    "nhan dc": "nhận được",
    "giup em": "giúp em",
    "giup e": "giúp em",
    "quy nay": "quý này",
    "thi co": "thì có",
    "nop ho so": "nộp hồ sơ",
    "nop hs": "nộp hồ sơ",
    "moi nhat": "mới nhất",
    "tai co so": "tại cơ sở",
    "co sao khong": "có sao không",
    "co sao ko": "có sao không",
    "thu tuc hanh chinh": "thủ tục hành chính",
    "thu tuc tiep nhan": "thủ tục tiếp nhận",
    "thu tuc": "thủ tục",
    "quy trinh thao tac": "quy trình thao tác",
    "quy trinh": "quy trình",
    "quy dinh chung": "quy định chung",
    "quy dinh": "quy định",
    "quy che luong thuong": "quy chế lương thưởng",
    "quy che lam viec": "quy chế làm việc",
    "quy che": "quy chế",
    "noi quy lao dong": "nội quy lao động",
    "noi quy cong ty": "nội quy công ty",
    "noi quy": "nội quy",
    "chinh sach nhan su": "chính sách nhân sự",
    "chinh sach phuc loi": "chính sách phúc lợi",
    "chinh sach": "chính sách",
    "dieu khoan hop dong": "điều khoản hợp đồng",
    "dieu khoan": "điều khoản",

    # Doanh nghiệp, Cơ quan, Tổ chức
    "cong ty co phan": "công ty cổ phần",
    "cong ty tnhh": "công ty TNHH",
    "cong ty": "công ty",
    "to chuc doanh nghiep": "tổ chức doanh nghiệp",
    "to chuc": "tổ chức",
    "co quan nha nuoc": "cơ quan nhà nước",
    "co quan quan ly": "cơ quan quản lý",
    "co quan": "cơ quan",
    "co so du lieu": "cơ sở dữ liệu",
    "co so ha tang": "cơ sở hạ tầng",
    "co so": "cơ sở",
    "co phan": "cổ phần",
    "co dong": "cổ đông",
    "doanh nghiep": "doanh nghiệp",
    "van phong": "văn phòng",
    "tru so chinh": "trụ sở chính",
    "tru so": "trụ sở",

    # Nhân sự, Tiền lương & Chức vụ
    "nhan vien chinh thuc": "nhân viên chính thức",
    "nhan vien thu viec": "nhân viên thử việc",
    "nhan vien": "nhân viên",
    "truong phong": "trưởng phòng",
    "pho phong": "phó phòng",
    "giam doc": "giám đốc",
    "pho giam doc": "phó giám đốc",
    "tong giam doc": "tổng giám đốc",
    "quan ly": "quản lý",
    "chuyen vien": "chuyên viên",
    "tro ly": "trợ lý",
    "chuc vu": "chức vụ",
    "chuc danh": "chức danh",
    "chuc nang nhiem vu": "chức năng nhiệm vụ",
    "chuc nang": "chức năng",
    "nhiem vu": "nhiệm vụ",
    "tien luong thang 13": "tiền lương tháng 13",
    "tien luong": "tiền lương",
    "phu cap an trua": "phụ cấp ăn trưa",
    "phu cap trach nhiem": "phụ cấp trách nhiệm",
    "phu cap": "phụ cấp",
    "tien thuong tet": "tiền thưởng tết",
    "thuong tet": "thưởng tết",
    "tien thuong": "tiền thưởng",
    "nghi phep nam": "nghỉ phép năm",
    "nghi phep": "nghỉ phép",
    "nghi thai san": "nghỉ thai sản",
    "nghi om dau": "nghỉ ốm đau",
    "nghi om": "nghỉ ốm",
    "nghi viec rieng": "nghỉ việc riêng",
    "nghi viec": "nghỉ việc",
    "thoi viec": "thôi việc",
    "sa thai": "sa thải",
    "boi thuong thiet hai": "bồi thường thiệt hại",
    "boi thuong": "bồi thường",
    "thoi gian thu viec": "thời gian thử việc",
    "thu viec": "thử việc",

    # Thuế, Kế toán & Tài chính
    "hoa don dien tu": "hóa đơn điện tử",
    "hoa don gia tri gia tang": "hóa đơn giá trị gia tăng",
    "hoa don": "hóa đơn",
    "dien tu": "điện tử",
    "dieu chinh hoa don": "điều chỉnh hóa đơn",
    "dieu chinh": "điều chỉnh",
    "sai sot hoa don": "sai sót hóa đơn",
    "sai sot": "sai sót",
    "sai mst": "sai MST",
    "ma so thue": "mã số thuế",
    "thue thu nhap ca nhan": "thuế thu nhập cá nhân",
    "thue thu nhap doanh nghiep": "thuế thu nhập doanh nghiệp",
    "thue gia tri gia tang": "thuế giá trị gia tăng",
    "thu nhap ca nhan": "thu nhập cá nhân",
    "thu nhap doanh nghiep": "thu nhập doanh nghiệp",
    "gia tri gia tang": "giá trị gia tăng",
    "ke khai thue": "kê khai thuế",
    "ke khai": "kê khai",
    "nop thue dien tu": "nộp thuế điện tử",
    "nop thue": "nộp thuế",
    "quyet toan thue": "quyết toán thuế",
    "quyet toan": "quyết toán",
    "hoan thue": "hoàn thuế",
    "mien thue": "miễn thuế",
    "giam thue": "giảm thuế",
    "tra cuu thue": "tra cứu thuế",
    "tra cuu hoa don": "tra cứu hóa đơn",
    "kiem tra giam sat": "kiểm tra giám sát",
    "kiem tra": "kiểm tra",
    "thanh tra phap ly": "thanh tra pháp lý",
    "thanh tra": "thanh tra",
    "bao cao tai chinh": "báo cáo tài chính",
    "bao cao": "báo cáo",
    "tai chinh doanh nghiep": "tài chính doanh nghiệp",
    "tai chinh": "tài chính",
    "tai san co dinh": "tài sản cố định",
    "tai san": "tài sản",
    "chi phi quan ly": "chi phí quản lý",
    "chi phi": "chi phí",
    "thanh toan luong": "thanh toán lương",
    "thanh toan": "thanh toán",
    "tam ung luong": "tạm ứng lương",
    "tam ung": "tạm ứng",
    "tai khoan ngan hang": "tài khoản ngân hàng",
    "tai khoan": "tài khoản",
    "ngan hang": "ngân hàng",
    "giao dich ngan hang": "giao dịch ngân hàng",
    "giao dich": "giao dịch",

    # Giấy tờ & Hành chính
    "can cuoc cong dan": "căn cước công dân",
    "can cuoc": "căn cước",
    "cong dan": "công dân",
    "chung minh nhan dan": "chứng minh nhân dân",
    "giay phep kinh doanh": "giấy phép kinh doanh",
    "giay chung nhan": "giấy chứng nhận",
    "giay to tuy than": "giấy tờ tùy thân",
    "giay to": "giấy tờ",
    "chung tu ke toan": "chứng từ kế toán",
    "chung tu": "chứng từ",
    "bien ban ban giao": "biên bản bàn giao",
    "bien ban": "biên bản",
    "thong bao moi": "thông báo mới",
    "thong bao": "thông báo",
    "van ban phap quy": "văn bản pháp quy",
    "van ban": "văn bản",
    "ho so nhan su": "hồ sơ nhân sự",
    "ho so": "hồ sơ",
    "quyet dinh bo nhiem": "quyết định bổ nhiệm",
    "quyet dinh": "quyết định",
    "thong tu huong dan": "thông tư hướng dẫn",
    "thong tu": "thông tư",
    "nghi dinh chinh phu": "nghị định chính phủ",
    "nghi dinh": "nghị định",
    "nghi quyet": "nghị quyết",
    "cong van": "công văn",

    # Ngữ cảnh hành động
    "thoi gian lam viec": "thời gian làm việc",
    "thoi gian": "thời gian",
    "dia chi tru so": "địa chỉ trụ sở",
    "dia chi": "địa chỉ",
    "so dien thoai": "số điện thoại",
    "ap dung quy dinh": "áp dụng quy định",
    "ap dung": "áp dụng",
    "hieu luc thi hanh": "hiệu lực thi hành",
    "hieu luc": "hiệu lực",
    "het han hop dong": "hết hạn hợp đồng",
    "het han": "hết hạn",
    "gia han hop dong": "gia hạn hợp đồng",
    "gia han": "gia hạn",
    "huy bo quyet dinh": "hủy bỏ quyết định",
    "huy bo": "hủy bỏ",
    "thay the van ban": "thay thế văn bản",
    "thay the": "thay thế",
    "sua doi bo sung": "sửa đổi bổ sung",
    "sua doi": "sửa đổi",
    "bo sung": "bổ sung",
    "tam dung hop dong": "tạm dừng hợp đồng",
    "tam dung": "tạm dừng",
    "cham dut hop dong": "chấm dứt hợp đồng",
    "cham dut": "chấm dứt",
    "thuc hien cong viec": "thực hiện công việc",
    "thuc hien": "thực hiện",
    "trien khai du an": "triển khai dự án",
    "trien khai": "triển khai",
    "phat trien": "phát triển",
    "giai quyet khieu nai": "giải quyết khiếu nại",
    "giai quyet": "giải quyết",
    "xu ly vi pham": "xử lý vi phạm",
    "xu ly": "xử lý",
    "hoan thanh nhiem vu": "hoàn thành nhiệm vụ",
    "hoan thanh": "hoàn thành",
    "ket qua danh gia": "kết quả đánh giá",
    "ket qua": "kết quả",
    "danh gia hieu qua": "đánh giá hiệu quả",
    "danh gia": "đánh giá",
    "nghiem thu du an": "nghiệm thu dự án",
    "nghiem thu": "nghiệm thu",
    "ban giao cong viec": "bàn giao công việc",
    "ban giao": "bàn giao",
    "cam ket bao mat": "cam kết bảo mật",
    "cam ket": "cam kết",
    "thoa thuan lao dong": "thỏa thuận lao động",
    "thoa thuan": "thỏa thuận",

    # Câu hỏi thường gặp & nghi vấn
    "khi nao ap dung": "khi nào áp dụng",
    "khi nao": "khi nào",
    "nhu the nao": "như thế nào",
    "tai sao lai": "tại sao lại",
    "tai sao": "tại sao",
    "bao nhieu tien": "bao nhiêu tiền",
    "bao nhieu": "bao nhiêu",
    "o dau": "ở đâu",
    "co duoc huong": "có được hưởng",
    "co duoc khong": "có được không",
    "co duoc": "có được",
    "khong duoc phep": "không được phép",
    "khong duoc": "không được",
    "phai lam sao": "phải làm sao",
    "lam the nao de": "làm thế nào để",
    "lam the nao": "làm thế nào",
    "lam sao": "làm sao",
    "lam viec tai nha": "làm việc tại nhà",
    "lam viec": "làm việc",
    "lam gi de": "làm gì để",
    "lam gi": "làm gì",
    "nam nay": "năm nay",
    "nam ngoai": "năm ngoái",
    "nam toi": "năm tới",
    "nam gioi": "nam giới",
    "tai lieu tham khao": "tài liệu tham khảo",
    "tai lieu": "tài liệu",
    "tai nan lao dong": "tai nạn lao động",
    "tai nan": "tai nạn",
    "thien tai dich benh": "thiên tai dịch bệnh",
    "thien tai": "thiên tai",
    "tai day": "tại đây",
    "tai nha": "tại nhà",
    "tai co quan": "tại cơ quan",
    "co the duoc": "có thể được",
    "co the": "có thể",
    "co hoi phat trien": "cơ hội phát triển",
    "co hoi": "cơ hội",
}

for raw_k, canonical_v in ADDITIONAL_PHRASES.items():
    DIACRITICS_PHRASE_MAP[raw_k] = canonical_v


# ==============================================================================
# UNAMBIGUOUS SINGLE WORDS (Grammatical & functional particles)
# Ambiguous single words ('co', 'lam', 'nam', 'tai', 'do') are excluded.
# ==============================================================================
DIACRITICS_WORD_MAP: Dict[str, str] = {
    "thue": "thuế",
    "luat": "luật",
    "dieu": "điều",
    "khoan": "khoản",
    "diem": "điểm",
    "ngay": "ngày",
    "thang": "tháng",
    "duoc": "được",
    "khong": "không",
    "la": "là",
    "va": "và",
    "cua": "của",
    "ve": "về",
    "voi": "với",
    "tu": "từ",
    "den": "đến",
    "tren": "trên",
    "duoi": "dưới",
    "truoc": "trước",
    "hoac": "hoặc",
    "neu": "nếu",
    "thi": "thì",
    "nhung": "nhưng",
    "vi": "vì",
    "de": "để",
    "nay": "này",
    "kia": "kia",
    "nao": "nào",
    "dau": "đâu",
    "tet": "tết",
}

# Legitimate level-tone (thanh ngang) words to prevent false unaccented detection
VIETNAMESE_LEVEL_TONE_WORDS: Set[str] = {
    "tra", "cho", "con", "anh", "em", "hoa", "ong", "ba", "tin", "xem", "xin",
    "cam", "on", "can", "ban", "muon", "khong", "song", "long", "dong", "trung",
    "nam", "bac", "tay", "minh", "quan", "an", "chan", "vai", "chu", "duong",
    "trang", "den", "vang", "xanh", "nau", "ca", "da", "di", "ra", "vao", "theo",
    "sau", "qua", "mau", "mang", "giao", "cong", "ty", "che", "do", "hop",
    "phong", "bien", "van", "ban", "viec", "chinh", "luong", "thuong", "nhan",
    "thai", "san", "thao", "tac", "khu", "vuc",
}
