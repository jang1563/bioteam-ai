# BioTeam-AI 바이오인포매틱스 벤치마크 리서치

> **목적**: 공개된 논문 데이터로 W9 에이전트 분석 결과 vs 논문 결과 비교
> **작성일**: 2026-02-27
> **상태**: 초안 (리서치 에이전트 결과 반영 예정)

---

## 1. 핵심 아이디어 정리

### 벤치마크 구조

```
공개 논문 데이터 (GEO / Zenodo / 보충 자료)
        ↓
  W9 에이전트 분석
        ↓
  에이전트 결과 vs 논문 결과 비교
        ↓
  점수화 → 성능 지표 → 개선 방향
```

### Ground Truth 문제

논문 결과가 항상 "정답"은 아님:
- **True Positive**: 논문 결과가 실험적으로 검증된 경우 → 높은 신뢰도 ground truth
- **Provisional Ground Truth**: 통계적으로 잘 설계된 논문 → 중간 신뢰도
- **Soft Ground Truth**: 재현 논문(replication study)이 있는 경우 → 가장 강함
- **Disputed**: 후속 연구로 번복된 결과 → 평가 제외 또는 별도 처리

**전략**: 여러 독립 연구에서 재현된 결과만 core benchmark로 사용

---

## 2. 알려진 공개 벤치마크 & 데이터셋

### 2.1 RNA-seq / 전사체 분석

#### SEQC / MAQC-III (FDA 벤치마크) ⭐⭐⭐⭐⭐
- **논문**: SEQC/MAQC-III Consortium. Nature Biotechnology, 2014
- **DOI**: 10.1038/nbt.2829
- **GEO 접근번호**: GSE47774
- **내용**: 4개 샘플 혼합 (A, B, C, D), 6개 플랫폼 비교
- **Known results**:
  - A vs B: ~1,000개 DEG (잘 알려진 목록)
  - 플랫폼 간 concordance 지표
- **에이전트 테스트**: count matrix → DESeq2/edgeR 분석 → 논문의 DEG 목록과 비교
- **장점**: FDA 공인, 극히 높은 재현성, 수백 편의 후속 연구
- **데이터 위치**: `https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE47774`

#### GTEx v8 / v10 ⭐⭐⭐⭐⭐
- **논문**: GTEx Consortium. Science, 2020 (v8)
- **DOI**: 10.1126/science.aaz1776
- **데이터**: `https://www.gtexportal.org/home/downloads/adult-gtex`
- **내용**: 54개 조직, 17,382개 샘플의 유전자 발현
- **Known results**:
  - 조직 특이적 발현 유전자 목록 (명확한 ground truth)
  - eQTL 목록 (각 조직별)
  - 발현 패턴 클러스터링
- **에이전트 테스트**: 특정 조직 발현 데이터 → 조직 마커 유전자 발견 → 논문 Supplementary Table과 비교
- **장점**: 누구나 알고 있는 조직 특이적 발현 패턴 (뇌 vs 간 vs 심장 등)

#### Benchmarking scRNA-seq (Zheng et al.) ⭐⭐⭐⭐
- **논문**: Zheng et al. Nature Communications, 2017
- **DOI**: 10.1038/ncomms14049
- **데이터**: 10X Genomics PBMC 3k/68k 데이터셋
- **GEO**: GSE132044 (scRNA-seq benchmark)
- **Known results**: 8개 면역세포 클러스터 마커 유전자
- **에이전트 테스트**: 세포 클러스터링 → 마커 유전자 → 논문 cell type 레이블과 비교

#### GEUVADIS ⭐⭐⭐⭐
- **논문**: Lappalainen et al. Nature, 2013
- **DOI**: 10.1038/nature12531
- **데이터**: `https://www.ebi.ac.uk/arrayexpress/experiments/E-GEUV-1/`
- **내용**: 465명의 RNA-seq + genotype → eQTL
- **Known results**: 1,953개 유전자의 cis-eQTL (FDR<5%)
- **에이전트 테스트**: 특정 유전자의 eQTL 분석 → 논문 결과 비교

---

### 2.2 유전체 변이 분석 (GWAS / WGS)

#### GIAB (Genome in a Bottle) ⭐⭐⭐⭐⭐
- **기관**: NIST
- **웹사이트**: `https://www.nist.gov/programs-projects/genome-bottle`
- **데이터**: `ftp://ftp-trace.ncbi.nlm.nih.gov/giab/ftp/`
- **Reference samples**: HG001 (NA12878), HG002-HG007
- **내용**: 6가지 기술(Illumina/PacBio/Nanopore 등)로 확인된 variant call gold standard
- **Known results**: HG001 기준 ~3.2M SNP, ~500K INDEL (high-confidence regions)
- **에이전트 테스트**: VCF 파일 → VEP 주석 → pathogenicity 분류 → GIAB gold standard 비교
- **장점**: NIST 공인, 변이 분석 분야 최고 기준

#### UK Biobank GWAS ⭐⭐⭐⭐
- **웹사이트**: `https://www.ukbiobank.ac.uk/`
- **내용**: 500,000명 유전체 + 표현형 데이터
- **GWAS Catalog**: `https://www.ebi.ac.uk/gwas/` — 공개된 GWAS 결과 집약
- **Known results**: 키(height)의 GWAS → ~12,000개 SNP (well-established)
- **에이전트 테스트**: GWAS summary statistics → gene mapping → pathway 분석 → 논문 비교
- **Practical subset**: 키 또는 BMI GWAS (결과가 매우 잘 알려진 표현형)

#### ClinGen / ClinVar 검증 ⭐⭐⭐
- **웹사이트**: `https://clinvar.ncbi.nlm.nih.gov/`
- **내용**: 임상 변이 병원성 분류 (Pathogenic / Benign / VUS)
- **Known results**: BRCA1/2 변이 분류 (매우 잘 연구됨)
- **에이전트 테스트**: 특정 변이 목록 → VEP + ACMG 분류 → ClinVar와 일치율 측정

---

### 2.3 경로 분석 / 기능 농축 (GO / KEGG)

#### Canonical Pathway Ground Truth ⭐⭐⭐⭐
- **전략**: 논문에서 잘 알려진 DEG 목록을 입력 → GO 분석 결과가 예상 경로를 찾는지 확인
- **예시**:
  - 암세포 vs 정상세포 DEG → PI3K/mTOR, 세포 분열 경로 (알려진 결과)
  - 면역 자극 DEG → NF-κB, IFN 신호 경로 (알려진 결과)
  - BRCA1 변이 세포 → DNA 손상 수복 경로 (알려진 결과)
- **데이터 출처**: 각 논문 보충 자료 (Supplementary Table)

#### MSigDB Gene Sets ⭐⭐⭐⭐
- **웹사이트**: `https://www.gsea-msigdb.org/gsea/msigdb`
- **내용**: 33,000+ 큐레이션 유전자 세트 (Hallmark 50개 + C2 canonical pathways)
- **Known results**: 각 Hallmark gene set의 정의된 유전자 목록
- **에이전트 테스트**: 유전자 목록 → GSEA → Hallmark 경로 발견 여부 비교

---

### 2.4 단백질 / 구조 분석

#### AlphaFold2 Benchmark ⭐⭐⭐⭐
- **논문**: Jumper et al. Nature, 2021
- **DOI**: 10.1038/s41586-021-03819-2
- **데이터**: CASP14 targets, PDB 검증 구조
- **Known results**: TM-score > 0.9 for most targets
- **에이전트 테스트**: 아미노산 서열 → AlphaFold 구조 예측 품질 평가 → CASP14 결과 비교

#### STRING-DB Network (잘 검증된 단백질 상호작용) ⭐⭐⭐
- **웹사이트**: `https://string-db.org/`
- **내용**: 67,000종, 3,000M 단백질 상호작용
- **Known results**: TP53 interactome, BRCA1 복합체 (실험 검증)
- **에이전트 테스트**: 단백질 목록 → 네트워크 분석 → Hub 유전자 발견 → STRING 고신뢰 상호작용과 비교

---

### 2.5 멀티오믹스 통합 분석

#### TCGA Pan-Cancer (TCGA Research Network) ⭐⭐⭐⭐⭐
- **논문**: Hoadley et al. Cell, 2018
- **DOI**: 10.1016/j.cell.2018.03.022
- **데이터**: `https://portal.gdc.cancer.gov/`
- **내용**: 33개 암종, 11,000명 환자의 DNA + RNA + protein + methylation
- **Known results**:
  - 암 분자 클러스터 (28개 클러스터로 분류)
  - 공통 암 드라이버 변이 (TP53, KRAS, PTEN, PIK3CA)
  - 암종별 발현 프로파일
- **에이전트 테스트**: 특정 암종 RNA-seq → 분자 서브타입 분류 → 논문 Table 비교
- **Practical entry point**: TCGA BRCA (유방암) 500샘플 → PAM50 서브타입 분류

#### CCLE (Cancer Cell Line Encyclopedia) ⭐⭐⭐⭐
- **웹사이트**: `https://depmap.org/portal/`
- **논문**: Ghandi et al. Nature, 2019
- **DOI**: 10.1038/s41586-019-1186-3
- **내용**: 1,400개 세포주, 약물 반응 + 유전체
- **Known results**: KRAS 변이 → MEK 억제제 민감도 (확립된 결과)
- **에이전트 테스트**: 유전자 발현 + 변이 → 약물 반응 예측 → DepMap 결과 비교

---

### 2.6 DREAM Challenges (경쟁 벤치마크)

> DREAM은 블라인드 예측 챌린지로 공개 리더보드와 gold standard가 있음

| Challenge | 연도 | 주제 | 데이터 위치 |
|-----------|------|------|------------|
| DREAM5 Network Inference | 2010 | GRN 추론 | `https://www.synapse.org/DREAM5` |
| DREAM Sub-Challenge (NCI-DREAM) | 2012 | 약물 조합 | Synapse |
| DREAM Mutation Effect | 2017 | 변이 기능 예측 | Synapse |
| DREAM Single Cell | 2019 | scRNA 경로 추론 | `https://www.synapse.org/DREAM_sc` |
| CASP (단백질 구조) | 2020-2024 | 구조 예측 | `https://predictioncenter.org/` |

- **접근**: `https://dreamchallenges.org/` — 대부분 공개 데이터 + 공개 평가 코드
- **장점**: 명확한 리더보드, 여러 방법론과 직접 비교 가능

---

## 3. 비교 가능한 AI 에이전트 시스템

### 3.1 일반 AI Scientist 시스템

| 시스템 | 기관 | 특징 | 관련 논문 |
|--------|------|------|----------|
| **The AI Scientist** | Sakana AI | 아이디어 → 실험 → 논문 생성, NeurIPS 2024 발표 | arXiv:2408.06292 |
| **AI Researcher** (Scientist-Bench) | 여러 기관 | 과학 논문 기반 QA + 분석 평가 | arXiv:2410.18652 |
| **PaperBench** | OpenAI | NeurIPS 논문 재현 벤치마크 | arXiv:2504.01848 |
| **FrontierMath** / **FrontierScience** | Epoch AI | 과학 문제 해결 벤치마크 | 2024 |
| **ResearchAgent** | KAIST | 연구 아이디어 → 검증 | arXiv:2404.07738 |

### 3.2 바이오인포매틱스 특화 AI

| 시스템 | 특징 | 비교 관련성 |
|--------|------|------------|
| **BioAgent** (BioGPT 기반) | 바이오 QA | 제한적 (QA만) |
| **GenePT** | 유전자 임베딩 + GPT-4 | scRNA-seq 분석 |
| **scGPT** | scRNA-seq 특화 파운데이션 모델 | 세포 유형 분류 |
| **Geneformer** | 유전자 네트워크 LLM | 유전자 우선순위 결정 |
| **BioMedLM** / **BioMedBERT** | 바이오메디컬 텍스트 | 텍스트 기반만 |
| **ChatGSE** | GSE 데이터 자동 분석 | ⭐ 직접적으로 관련 |

### 3.3 ChatGSE — 가장 유사한 시스템

- **논문**: Lobentanzer et al. "Democratizing knowledge representation with BioCypher" 및 ChatGSE
- **GitHub**: `https://github.com/biocypher/ChatGSE` (현재 BioChatter)
- **특징**: GEO 데이터셋 → 자동 분석 → 해석
- **관련 논문**: arXiv:2305.06488
- **차이점**: BioTeam-AI보다 훨씬 단순한 파이프라인, 멀티에이전트 없음

### 3.4 PaperBench (OpenAI, 2025) — 가장 직접적인 벤치마크 방법론 참조

- **논문**: "PaperBench: Evaluating AI's Ability to Replicate AI Research" (2025)
- **방법**:
  1. NeurIPS 2024 논문 선택
  2. 저자에게 재현 체크리스트 작성 요청
  3. AI에게 코드 + 데이터로 논문 재현 시도
  4. 체크리스트 항목 달성도 점수화
- **바이오 적용 가능**: 바이오인포매틱스 논문에 동일 방법론 적용 가능

---

## 4. 실용적인 벤치마크 설계 제안

### 4.1 BioTeam-AI Benchmark v1.0 (Phase 7)

#### 설계 원칙

1. **Reproducibility First**: 독립적으로 재현된 결과만 ground truth로 사용
2. **Graded Scoring**: 정확한 일치(1.0) → 방향 일치(0.5) → 불일치(0.0)
3. **Multi-level Comparison**: Gene-level, pathway-level, biology-level 각각 평가
4. **"False Ground Truth" 처리**: 후속 논문으로 번복된 결과 플래그
5. **Cost-aware**: W9 분석 비용 vs 결과 품질 trade-off 측정

#### 벤치마크 세트 구조

```
BioTeam-AI-Bench/
├── datasets/
│   ├── rna_seq/
│   │   ├── maqc_seqc/          # FDA 벤치마크 (gold standard)
│   │   ├── gtex_tissue/        # 조직 특이적 발현
│   │   └── cancer_de/          # 암 DEG (TCGA 기반)
│   ├── variant/
│   │   ├── giab_hg001/         # Genome in a Bottle
│   │   └── clinvar_brca/       # BRCA1/2 분류
│   ├── pathway/
│   │   ├── known_cancer/       # 알려진 암 경로
│   │   └── immune_response/    # 면역 반응 경로
│   └── multiomics/
│       ├── tcga_brca/          # TCGA 유방암 서브타입
│       └── ccle_drug/          # 약물 반응 예측
├── ground_truth/
│   ├── {dataset}_expected.json  # 예상 결과 (논문 기반)
│   ├── {dataset}_metadata.json  # 논문 DOI, 신뢰도 등급
│   └── {dataset}_rubric.json    # 채점 기준
├── runners/
│   ├── run_benchmark.py         # 자동 실행 스크립트
│   └── score_results.py         # 결과 채점
└── results/
    └── {date}_{model}/          # 실행 결과 저장
```

#### Tier 1 벤치마크 (즉시 시작 가능)

| ID | 분석 유형 | 데이터셋 | 입력 | 기대 출력 | Ground Truth 신뢰도 |
|----|----------|---------|------|----------|-------------------|
| BIO-001 | RNA-seq DEA | MAQC-III (GSE47774) | Count matrix (A vs B) | DEG 목록 + fold change | ⭐⭐⭐⭐⭐ |
| BIO-002 | Tissue expression | GTEx v8 | 조직 발현 행렬 | 조직 마커 유전자 | ⭐⭐⭐⭐⭐ |
| BIO-003 | Variant annotation | GIAB HG001 VCF | 1000개 변이 VCF | 병원성 분류 | ⭐⭐⭐⭐⭐ |
| BIO-004 | GO enrichment | BRCA1-KO DEG 목록 | DEG list | DNA 손상 수복 경로 | ⭐⭐⭐⭐ |
| BIO-005 | Cancer subtype | TCGA BRCA 500샘플 | RNA-seq matrix | PAM50 서브타입 | ⭐⭐⭐⭐⭐ |
| BIO-006 | scRNA clustering | 10X PBMC 3k | Cell × gene matrix | 8개 면역세포 타입 | ⭐⭐⭐⭐ |
| BIO-007 | eQTL validation | GTEx Brain 결과 | Gene + SNP list | cis-eQTL 목록 | ⭐⭐⭐⭐ |
| BIO-008 | PPI network | BRCA1 interactome | 단백질 목록 | Hub 단백질 (STRING) | ⭐⭐⭐ |

#### 채점 기준 (Rubric)

```python
class BenchmarkScore(BaseModel):
    # Gene-level: 교집합 / 합집합
    gene_overlap_jaccard: float       # 0.0 ~ 1.0
    gene_overlap_recall: float        # 논문 유전자 중 에이전트가 찾은 비율
    gene_overlap_precision: float     # 에이전트 결과 중 논문과 일치하는 비율

    # Pathway-level: 상위 경로 overlap
    top10_pathway_overlap: float      # 상위 10개 경로 Jaccard
    top3_pathway_match: bool          # 상위 3개 중 1개 이상 일치

    # Direction-level: 방향성 일치
    fold_change_correlation: float    # Pearson r (log2FC)
    direction_accuracy: float         # up/down 방향 일치율

    # Biology-level (LLM-as-judge)
    biological_coherence: float       # LLM이 평가한 생물학적 합리성 (0~1)
    novel_insight: float              # 논문에 없는 추가 발견의 가치

    # Meta
    cost_usd: float                   # 분석 비용
    runtime_seconds: float            # 실행 시간
    ground_truth_confidence: str      # "gold" / "silver" / "bronze"
```

#### 평가 지표 (최종 스코어)

```
BioAgent Score =
    0.30 × gene_recall (중요: 논문 결과를 얼마나 커버하는가)
  + 0.20 × pathway_overlap (경로 분석 정확도)
  + 0.20 × direction_accuracy (fold change 방향)
  + 0.15 × biological_coherence (LLM judge)
  + 0.10 × novel_insight (추가 발견 가치)
  - 0.05 × (cost_usd / 10)  # 비용 패널티

범위: 0.0 ~ 1.0
Gold Standard 기준: > 0.70 = 교수급, > 0.50 = 대학원생급, < 0.30 = 재작업 필요
```

---

### 4.2 현재 프로젝트 통합 vs 별도 프로젝트 고려

#### 옵션 A: 현재 프로젝트 내 통합 (권장)

**장점**:
- W9 runner가 이미 바이오인포매틱스 분석 파이프라인 완성
- Phase 3의 7개 API 클라이언트 (Ensembl, UniProt, STRING, GOenrichment 등) 즉시 활용
- CheckpointManager로 재개 가능
- 기존 test infrastructure 재사용

**구현 위치**:
```
backend/
├── app/
│   └── engines/
│       └── benchmark/           ← 신규
│           ├── __init__.py
│           ├── dataset_loader.py   # GEO, Zenodo 데이터 로더
│           ├── result_scorer.py    # 채점 로직
│           └── ground_truth.py     # GT 관리
├── data/
│   └── benchmarks/
│       ├── bio001_maqc/
│       ├── bio002_gtex/
│       └── ...
└── scripts/
    └── run_benchmark.py         # 벤치마크 실행 스크립트
```

**단점**: 프로젝트가 더 복잡해짐

#### 옵션 B: 별도 리포지토리

**장점**: 독립적 개발, 다른 에이전트 시스템과도 비교 가능
**단점**: 중복 코드, 유지보수 부담

#### 권장: 옵션 A (현재 프로젝트 내) + CLI 인터페이스

W9 runner를 그대로 사용하되, 벤치마크 데이터 로더 + 채점 엔진만 추가:
```bash
# 사용법
uv run python backend/scripts/run_benchmark.py \
  --suite bio001  \         # MAQC RNA-seq
  --budget 5.0   \          # $5 제한
  --compare-paper 10.1038/nbt.2829  # 비교 논문 DOI
```

---

### 4.3 단계별 구현 로드맵

#### Phase 7-A: 데이터 수집 및 GT 구축 (1주)

1. MAQC-III (GSE47774) count matrix 다운로드 + 논문 DEG 목록 수동 추출
2. GTEx v8 조직 마커 유전자 목록 (Supplementary Table에서)
3. GIAB HG001 high-confidence VCF 다운로드
4. 각 데이터셋에 `ground_truth.json` 파일 작성

#### Phase 7-B: Scorer 구현 (3일)

```python
# backend/app/engines/benchmark/result_scorer.py
class BenchmarkScorer:
    def score_gene_list(self, agent_genes: list[str], expected_genes: list[str]) -> GeneListScore
    def score_pathway_enrichment(self, agent_paths: list[str], expected_paths: list[str]) -> PathwayScore
    def score_variant_classification(self, agent_vcf: dict, expected_clinvar: dict) -> VariantScore
    def llm_judge_biological_coherence(self, agent_summary: str, paper_abstract: str) -> float
```

#### Phase 7-C: 첫 벤치마크 실행 (2일)

- BIO-001 (MAQC): W9 실행 → 채점 → 리포트
- 약점 파악 → 프롬프트 개선 → 재실행

#### Phase 7-D: 대시보드 통합 (선택)

프론트엔드에 "Benchmark" 페이지 추가:
- 각 벤치마크의 최신 점수
- 시간별 성능 추이
- 에이전트별 강/약점 시각화

---

## 5. 즉시 시작 가능한 파일럿 실험

### 파일럿: MAQC RNA-seq (BIO-001)

**비용**: ~$3 (W9 실행) + $0 (데이터 공개)

```bash
# Step 1: 데이터 다운로드
# GSE47774에서 count matrix 다운로드 (GEO FTP)
wget ftp://ftp.ncbi.nlm.nih.gov/geo/series/GSE47nnn/GSE47774/suppl/GSE47774_RAW.tar.gz

# Step 2: W9 실행 (데이터 준비 후)
uv run python backend/scripts/w9_benchmark.py \
  --dataset maqc_seqc \
  --input data/benchmarks/bio001_maqc/counts.csv \
  --expected data/benchmarks/bio001_maqc/ground_truth.json \
  --budget 3.0

# Step 3: 채점
# gene recall vs MAQC DEG gold standard
# pathway overlap vs 논문 Figure 2
```

**기대 결과 (from 논문)**:
- A vs B 비교: 1,012개 DEG (adjusted p < 0.001, |log2FC| > 1)
- 상위 경로: 면역/염증 관련 (MAQC mixture 특성)
- 플랫폼 간 Spearman r > 0.9

---

## 6. 참조 문헌 & 리소스

### 핵심 논문

| 논문 | 관련성 |
|------|--------|
| SEQC/MAQC-III Consortium (2014) Nat Biotechnol 32:903 | RNA-seq gold standard |
| GTEx Consortium (2020) Science 369:1318 | 조직 발현 atlas |
| GIAB Consortium (2022) Nat Biotechnol | Variant call ground truth |
| Jumper et al. (2021) Nature 596:583 | AlphaFold2 평가 |
| Zheng et al. (2017) Nat Commun 8:14049 | scRNA-seq benchmark |
| Hoadley et al. (2018) Cell 173:291 | TCGA Pan-cancer |
| Lundberg et al. (PaperBench, 2025) arXiv:2504.01848 | AI 논문 재현 벤치마크 |
| Lu et al. (AI Scientist, 2024) arXiv:2408.06292 | AI Scientist 방법론 |

### 유용한 데이터 포털

| 포털 | URL | 용도 |
|------|-----|------|
| GEO | ncbi.nlm.nih.gov/geo | RNA-seq, microarray 공개 데이터 |
| TCGA | portal.gdc.cancer.gov | 암 멀티오믹스 |
| GTEx | gtexportal.org | 조직 발현 + eQTL |
| GIAB | nist.gov/programs-projects/genome-bottle | 변이 ground truth |
| DREAM | dreamchallenges.org | 경쟁 벤치마크 |
| Synapse | synapse.org | DREAM 데이터 저장소 |
| DepMap | depmap.org | 세포주 약물 반응 |
| ENCODE | encodeproject.org | 기능 유전체 |

---

## 7. 최신 AI 에이전트 바이오인포매틱스 벤치마크 (2024–2026)

> 리서치 에이전트 완료 후 업데이트됨 (2026-02-27)

### 7.1 핵심 발견 요약

**현재 최고 AI 에이전트의 성능 수준 (2026년 기준)**:

| 벤치마크 | 최고 모델 | 정확도 | 비고 |
|---------|---------|--------|------|
| BixBench (실제 논문 분석) | Claude 3.5 Sonnet | **17%** | 최고 난이도 |
| scBench (scRNA-seq) | Claude Opus 4.6 | **52.8%** | 2026.02 최신 |
| BioAgent Bench (종합) | GPT-4o + o1 | ~40-60% | 에러 주입 시 급감 |
| GenoTEX (GEO 유전자 발현) | OpenAI o1 | AUROC 0.74 | 전문가 수준 |
| Biomni-Eval (QA 형식) | Biomni | 74-82% | QA 형식이므로 실제 분석과 다름 |

**핵심 시사점**: 실제 분석 작업(코드 실행 + 데이터 해석)은 아직 매우 어려움. QA 형식은 74%+이지만, 실제 데이터 분석은 17-53% 수준. **BioTeam-AI가 개선할 여지가 크다.**

---

### 7.2 주요 기존 벤치마크 (BioTeam-AI와 직접 비교 가능)

#### BixBench ⭐⭐⭐⭐⭐ (가장 중요)
- **논문**: FutureHouse (2025년 3월)
- **arXiv**: [2503.00096](https://arxiv.org/abs/2503.00096)
- **내용**: 실제 생물학 논문 53편에서 추출한 데이터 분석 시나리오 (~300개 질문)
- **방식**: 에이전트가 빈 Jupyter 노트북 + 원시 데이터 + 질문을 받고 자유롭게 분석
- **데이터**: 멀티오믹스 (전사체, 유전체, 단백질체) 공개 논문 기반
- **결과**: Claude 3.5 Sonnet **17%**, GPT-4o **9%**
- **BioTeam-AI 적용**: 이 53개 데이터셋을 그대로 사용하여 W9 성능 측정 가능
- **GitHub/데이터**: FutureHouse 공개 예정 (논문 참조)

#### scBench ⭐⭐⭐⭐⭐ (scRNA-seq 특화)
- **논문**: arXiv [2602.09063](https://arxiv.org/abs/2602.09063) (2026년 2월, 최신)
- **GitHub**: [latchbio/scbench](https://github.com/latchbio/scbench)
- **내용**: 394개 검증 가능한 scRNA-seq 문제
- **플랫폼**: 6개 시퀀싱 플랫폼 (BD Rhapsody, Chromium, CSGenetics, Illumina, MissionBio, ParseBio)
- **7개 카테고리**: QC, 정규화, 차원 축소, 클러스터링, 세포 유형 분류, DEA, 궤적 분석
- **결과**: Claude Opus 4.6 **52.8%** (최고), GPT 45.2%
- **플랫폼 효과**: 플랫폼 선택에 따라 40% 포인트 차이
- **BioTeam-AI 적용**: 즉시 사용 가능한 공개 벤치마크

#### GenoTEX ⭐⭐⭐⭐⭐ (GEO 유전자 발현)
- **논문**: arXiv [2406.15341](https://arxiv.org/abs/2406.15341) (MLCB 2025 Oral)
- **GitHub**: [Liu-Hy/GenoTex](https://github.com/Liu-Hy/GenoTex)
- **내용**: 전문가 큐레이션 LLM 에이전트 벤치마크 (GEO 데이터셋 기반)
- **전체 파이프라인**: 데이터셋 선택 → 전처리 → 통계 분석 → 유전자-특성 연관성
- **결과**: GenoAgent (o1) **AUROC 0.74** for GEO→유의미 유전자 발굴
- **BioTeam-AI 적용**: GEO 데이터 기반 파이프라인이 W9와 동일한 구조

#### BioAgent Bench ⭐⭐⭐⭐
- **논문**: arXiv [2601.21800](https://arxiv.org/html/2601.21800v1) (2025년 1월)
- **GitHub**: [bioagent-bench/bioagent-bench](https://github.com/bioagent-bench/bioagent-bench)
- **내용**: bulk RNA-seq, scRNA-seq, 변이 콜링, 메타유전체, 전사체 정량화, 비교 유전체학
- **특징**: LLM 기반 채점자 + **스트레스 테스트** (손상된 입력, 미끼 파일, 프롬프트 오염)
- **핵심 발견**: 최고 에이전트는 완전한 파이프라인 실행 가능하지만 에러 주입 시 급격히 저하
- **오픈소스**: 평가 코드 공개

#### ScienceAgentBench ⭐⭐⭐⭐ (ICLR 2025)
- **논문**: arXiv [2410.05080](https://arxiv.org/abs/2410.05080)
- **GitHub**: [OSU-NLP-Group/ScienceAgentBench](https://github.com/OSU-NLP-Group/ScienceAgentBench)
- **내용**: 44편의 동료 심사 논문에서 추출한 102개 태스크 (바이오인포매틱스 포함)
- **평가**: 자체 포함 Python 프로그램 출력 → 실행 + 코드 정확도 평가
- **결과**: OpenAI o1 (self-debug) **42.2%**, 일반 frontier LLM **32.4%**
- **컨테이너화**: 8 스레드로 30분 내 102개 태스크 전부 실행 가능

#### LAB-Bench ⭐⭐⭐⭐ (FutureHouse)
- **논문**: arXiv [2407.10362](https://arxiv.org/abs/2407.10362)
- **HuggingFace**: [futurehouse/lab-bench](https://huggingface.co/datasets/futurehouse/lab-bench)
- **내용**: 2,400+ 선택형 문제 (실제 생물학 연구 기술)
- **커버**: 문헌 회상, 그림 해석, DB 탐색, DNA/단백질 서열 조작
- **공개 부분집합**: HuggingFace에서 즉시 사용 가능

---

### 7.3 비교 가능한 AI 에이전트 시스템 (상세)

#### Biomni (Stanford, 2025) — 종합 바이오메디컬 AI
- **bioRxiv**: [2025.05.30.656746](https://www.biorxiv.org/content/10.1101/2025.05.30.656746v1)
- **GitHub**: [snap-stanford/Biomni](https://github.com/snap-stanford/Biomni)
- **태스크**: 변이 우선순위 결정, GWAS 인과 유전자 발견, 희귀 질환 진단, 약물 재목적화, scRNA-seq 세포 주석
- **Biomni-Eval1**: 10개 생물학 추론 태스크, 433개 인스턴스
- **성능**: DbQA **74.4%** (전문가 74.7%와 동등), SeqQA **81.9%** (전문가 78.8% 초과)

#### BiOmics (2026.01) — 멀티오믹스 특화
- **bioRxiv**: [2026.01.17.699830](https://www.biorxiv.org/content/10.64898/2026.01.17.699830v1)
- **아키텍처**: 이중 트랙 (명시적 추론 공간 + 잠재 임베딩 공간)
- **강점**: 간접 병인성 변이 발견, 참조 없는 세포 주석, 약물 재목적화 우선순위 결정

#### BioMaster (2025.01) — 멀티에이전트 워크플로우
- **bioRxiv**: [2025.01.23.634608](https://www.biorxiv.org/content/10.1101/2025.01.23.634608v1)
- **구조**: 계획자-실행자-검증자 에이전트 역할 분담
- **커버**: RNA-seq, ChIP-seq, scRNA-seq, Hi-C 처리
- **BioTeam-AI와 유사한 구조** — 벤치마크 비교 대상으로 적합

#### GenoMAS (2025.07) — 코드 기반 유전자 발현 분석
- **arXiv**: [2507.21035](https://arxiv.org/abs/2507.21035)
- **구조**: 6개 특화 LLM 에이전트 + 타입화된 메시지 전달 프로토콜
- **특징**: 구조화된 워크플로우 + 자율적 적응의 통합

#### BioAgents (Nature Sci Rep, 2025) — 소형 모델 특화
- **논문**: [Scientific Reports](https://www.nature.com/articles/s41598-025-25919-z)
- **특징**: 소형 LLM + 바이오인포매틱스 파인튜닝 + RAG
- **장점**: 로컬 실행 (프라이버시 보호), 전용 데이터 처리

---

### 7.4 단일세포 파운데이션 모델 비판적 평가 (2025)

> ⚠️ 중요: 2025년 Nature급 논문들이 scRNA-seq 파운데이션 모델의 한계를 지적

#### 제로샷 평가 (Genome Biology, 2025)
- **URL**: [genomebiology.biomedcentral.com](https://genomebiology.biomedcentral.com/articles/10.1186/s13059-025-03574-x)
- **핵심 발견**: Geneformer, scGPT가 제로샷에서 단순한 방법에 패배
- **태스크**: 세포 유형 주석, 배치 통합, 약물 민감도 예측, 암세포 식별

#### 유전자 교란 예측 (Nature Methods, 2025)
- **URL**: [nature.com/s41592-025-02772-6](https://www.nature.com/articles/s41592-025-02772-6)
- **핵심 발견**: scBERT, Geneformer, scGPT 계열 모델이 **선형 회귀**보다 일관적으로 좋지 않음
- **중요성**: BioTeam-AI의 비교 시 딥러닝 모델과의 비교에서 단순 기준선 포함 필수

---

### 7.5 DREAM Challenges 최신 현황 (2025)

#### Random Promoter DREAM Challenge (Nature Biotechnology, 2025)
- **논문**: [nature.com/s41587-024-02414-w](https://www.nature.com/articles/s41587-024-02414-w)
- **Synapse**: [syn28469146](https://www.synapse.org/#!Synapse:syn28469146/wiki/617075)
- **내용**: 수백만 개 무작위 효모 프로모터 서열 → 유전자 발현 예측
- **결과**: 모든 상위 모델이 신경망 사용; Prix Fixe 모듈식 모델 비교 프레임워크

#### 암 대량 데이터 분리 DREAM Challenge (NCI, 2025)
- **URL**: [datascience.cancer.gov](https://datascience.cancer.gov/news-events/news/dream-challenge-benchmarks-approaches-deciphering-bulk-genetic-cancer-data)
- **내용**: 암 대량 유전 데이터 해석을 위한 접근법 벤치마킹

---

### 7.6 BioTeam-AI를 위한 전략적 권고

#### 즉시 채택 가능한 기존 벤치마크 (우선순위 순)

1. **scBench** (arXiv 2602.09063) — scRNA-seq 394개 문제, 즉시 비교 가능, Claude Opus 4.6 52.8% 기준
2. **GenoTEX** (arXiv 2406.15341) — GEO 기반, GenoAgent(o1) AUROC 0.74 기준
3. **BioAgent Bench** — RNA-seq/변이콜링, 오픈소스 채점 포함
4. **ScienceAgentBench** — 102개 문제, ICLR 공신력

#### BioTeam-AI만의 차별점 활용

기존 벤치마크와 달리 BioTeam-AI는:
- **멀티에이전트 협업**: 10개 도메인 에이전트 병렬 실행 (다른 시스템은 단일 에이전트)
- **RCMXT 근거 평가**: 에이전트 결과의 근거 신뢰도 자동 평가 (고유 기능)
- **CheckpointManager**: 장시간 분석 재개 가능 (다른 시스템은 단일 세션)
- **Anti-hallucination**: PTC 결과에 `_source`/`_retrieved_at` 태그 (검증 가능성)

#### 새로운 벤치마크 기여 기회

기존 벤치마크의 빈틈:
- **멀티에이전트 협업 효과**: 에이전트 수 vs 성능 trade-off 측정 벤치마크 없음
- **비용 효율성**: 분석 비용($) vs 결과 품질 벤치마크 없음
- **한국어 생물학 논문**: 비영어권 논문에서 데이터 추출 벤치마크 없음
- **Hallucination in bio**: 생물학적 주장의 hallucination 탐지 벤치마크 부족

---

### 7.7 참조 문헌 전체 목록 (최신순)

| 논문 | 연도 | arXiv/DOI |
|------|------|-----------|
| scBench: Evaluating AI Agents on scRNA-seq | 2026.02 | [2602.09063](https://arxiv.org/abs/2602.09063) |
| BiOmics: Foundational Agent for Multi-omics | 2026.01 | [bioRxiv](https://www.biorxiv.org/content/10.64898/2026.01.17.699830v1) |
| BixBench: Comprehensive Benchmark for LLM in CompBio | 2025.03 | [2503.00096](https://arxiv.org/abs/2503.00096) |
| GenoMAS: Multi-Agent for Gene Expression Analysis | 2025.07 | [2507.21035](https://arxiv.org/abs/2507.21035) |
| BioML-bench: End-to-End Biomedical ML Evaluation | 2025.09 | [bioRxiv](https://www.biorxiv.org/content/10.1101/2025.09.01.673319v2) |
| Biomni: General-Purpose Biomedical AI Agent | 2025.05 | [bioRxiv](https://pmc.ncbi.nlm.nih.gov/articles/PMC12157518/) |
| BioMaster: Multi-agent for Bioinformatics Workflow | 2025.01 | [bioRxiv](https://www.biorxiv.org/content/10.1101/2025.01.23.634608v1) |
| BioAgent Bench: AI Agent Evaluation Suite | 2025.01 | [2601.21800](https://arxiv.org/html/2601.21800v1) |
| BioAgents: Multi-Agent Bioinformatics | 2025 | Nat Sci Rep |
| Zero-shot evaluation of scFMs | 2025 | [Genome Biol](https://genomebiology.biomedcentral.com/articles/10.1186/s13059-025-03574-x) |
| Gene perturbation prediction vs baselines | 2025 | [Nat Methods](https://www.nature.com/articles/s41592-025-02772-6) |
| Random Promoter DREAM Challenge | 2025 | [Nat Biotechnol](https://www.nature.com/articles/s41587-024-02414-w) |
| Quartet RNA-seq Benchmarking | 2024 | [Nat Commun](https://www.nature.com/articles/s41467-024-50420-y) |
| ScienceAgentBench (ICLR 2025) | 2024 | [2410.05080](https://arxiv.org/abs/2410.05080) |
| GenoTEX: LLM Agent Benchmark for GEO (MLCB 2025) | 2024 | [2406.15341](https://arxiv.org/abs/2406.15341) |
| LAB-Bench: LM Biology Research Capabilities | 2024 | [2407.10362](https://arxiv.org/abs/2407.10362) |
| NGS Downstream Analysis Agentic AI | 2024.12 | [2512.09964](https://arxiv.org/abs/2512.09964) |

---

---

## 8. AutoBA — 가장 직접적인 비교 대상 시스템

### AutoBA (Advanced Science, 2024)
- **논문**: Advanced Science (2024), DOI: [10.1002/advs.202407094](https://doi.org/10.1002/advs.202407094) (PMC11600294)
- **GitHub**: [JoshuaChou2018/AutoBA](https://github.com/JoshuaChou2018/AutoBA)
- **공개 성능 지표**:
  - 계획 생성 성공률: **90%**
  - 코드 생성 성공률: **82.5%**
  - End-to-end 분석 성공률: **65%** (40개 멀티오믹스 태스크)
- **지원 분석**: WGS/WES, ChIP-seq, RNA-seq, scRNA-seq, 공간 전사체
- **Ground truth 방법**: 원본 데이터 논문의 published 결과와 직접 비교
- **에러 처리**: Automated Code Repair (ACR) — 실패 시 자동 재시도

**BioTeam-AI vs AutoBA 비교**:

| 기능 | BioTeam-AI | AutoBA |
|------|-----------|--------|
| 멀티에이전트 | ✅ 10개 도메인 에이전트 | ❌ 단일 에이전트 |
| 체크포인트/재개 | ✅ CheckpointManager | ❌ 없음 |
| RCMXT 근거 평가 | ✅ 고유 기능 | ❌ 없음 |
| 반할루시네이션 | ✅ PTC + _source 태깅 | ❌ 없음 |
| 비용 추적 | ✅ 실시간 추적 | ❌ 없음 |
| End-to-end 성공률 | ? (측정 예정) | 65% |
| 코드 생성 | ✅ PTC sandbox | ✅ direct exec |

---

## 9. Ground Truth 신뢰성 처리 방법론 (기존 연구의 전략)

논문 결과가 항상 "정답"이 아닌 문제를 기존 연구들은 다음 4가지 방법으로 해결:

### 전략 1: 비율 기반 ground truth (Quartet/MAQC 방식)
- 절대적 진실 주장 대신 **알려진 혼합 비율에서 기대 fold-change 계산**
- 방향성 + 크기가 수학적 예측과 일치하면 "정답"
- 생물학적 주장에 의존하지 않음 → 논란 없는 ground truth

### 전략 2: 다중 기술 합의 (GIAB 방식)
- Illumina + PacBio HiFi + ONT + 10X linked-reads + BioNano 등 **직교 기술들의 합의**
- 모든 기술이 동의하는 변이만 "high-confidence" 구역으로 지정
- 불일치 구역은 명시적으로 벤치마크에서 제외

### 전략 3: 전문가 독립 주석 (GenoTEX/BixBench 방식)
- 전문 바이오인포매틱스 연구자가 데이터셋을 독립적으로 분석
- 분석 단계, 중간 결과, 최종 결론을 모두 기록
- AI는 전문가의 문서화된 파이프라인 선택 및 결론과 비교

### 전략 4: 기능적 검증 교차 참조 (DREAM 방식)
- 합성 데이터: BAMSurgeon으로 변이 주입 → 수학적으로 확실한 ground truth
- 실제 데이터: 커뮤니티 상위 방법들의 합의에서 "진실 세트" 파생

**BioTeam-AI 권장 전략**: 전략 1 + 3 혼합
- 정량적 태스크 (DEG 목록, FC 방향): 전략 1 (비율/방향 기반)
- 해석적 태스크 (경로 분석, 생물학적 의미): 전략 3 (전문가 주석 + LLM-as-judge)

---

## 10. 종합 데이터셋 요약 테이블

| 도메인 | 데이터셋 | 접근번호/URL | Ground Truth 유형 |
|--------|---------|------------|-----------------|
| RNA-seq DE | SEQC/MAQC-III | GEO GSE47792 | ERCC 비율, 혼합 유도 DE |
| RNA-seq DE | Quartet 2024 | Nat Commun [10.1038/s41467-024-50420-y](https://doi.org/10.1038/s41467-024-50420-y) | 가족 비율 기반 DE |
| eQTL/RNA-seq | GEUVADIS | EBI E-GEUV-1 | 공개 cis-eQTL 테이블 |
| 조직 eQTL | GTEx V8 | dbGaP phs000424.v8.p2 | 조직별 eQTL 쌍 |
| 생식세포 변이 | GIAB HG002 | NIST/SRA PRJNA200694 | 다중 기술 truth VCF |
| 체세포 변이 | DREAM SMC-DNA | Synapse.org | BAMSurgeon 주입 GT |
| 변이 병원성 | ClinVar | ncbi.nlm.nih.gov/clinvar | 전문가 큐레이션 P/LP vs B/LB |
| scRNA-seq 주석 | Tabula Sapiens | HCA Explorer | 전문가 주석 세포 유형 |
| scRNA-seq 주석 | 10X PBMC 3K/8K | 10X Genomics 웹사이트 | Seurat 정규 매핑 |
| 범암종 | TCGA PanCanAtlas | gdc.cancer.gov/pancanatlas | 28개 published 분석 논문 |
| 단백질체 | CPTAC 11-cancer | proteomics.cancer.gov | Published CPTAC 논문 |
| 경로 농축 | Buzzao 2024 | Briefings Bioinformatics bbae069 | 82개 데이터셋 전문가 큐레이션 |
| 유전자 발현 AI | GenoTEX | github.com/Liu-Hy/GenoTEX | 바이오인포매틱스 전문가 주석 |
| 에이전트 벤치마크 | BixBench | arXiv 2503.00096 | 전문가 유도 결정론적 |
| 에이전트 벤치마크 | BioAgentBench | arXiv 2601.21800 | LLM 채점자 + 파이프라인 아티팩트 |
| 종합 바이오메디컬 | Biomni 8 태스크 | biomni.stanford.edu | Published 논문 골드 스탠다드 |

---

*작성: BioTeam-AI Planning, 2026-02-27 (리서치 에이전트 결과 통합)*
*관련 계획: `docs/planning/plan_v4.md` Phase 7 예정*
