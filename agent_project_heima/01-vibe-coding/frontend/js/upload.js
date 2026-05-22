/**
 * 知识库管理页面逻辑
 * 功能：学科选择、文件/文件夹拖拽上传、批量上传、已入库文档列表
 */

const API_BASE = '/api/v1';

/* ── 状态 ─────────────────────────────────────────────────────── */
let selectedSubject = '';      // 当前选中的学科代码
let selectedFiles = [];        // 待上传的 File 对象列表
let currentPage = 1;           // 文档列表当前页
let totalDocs = 0;             // 文档总数（用于分页）
const PAGE_SIZE = 15;          // 每页条数

/* ── DOM 引用 ──────────────────────────────────────────────────── */
const subjectChips    = document.getElementById('subject-chips');
const dropzone        = document.getElementById('dropzone');
const fileInput       = document.getElementById('file-input');
const folderInput     = document.getElementById('folder-input');
const pickFilesBtn    = document.getElementById('pick-files-btn');
const pickFolderBtn   = document.getElementById('pick-folder-btn');
const fileListSection = document.getElementById('file-list-section');
const fileCountLabel  = document.getElementById('file-count-label');
const fileList        = document.getElementById('file-list');
const clearFilesBtn   = document.getElementById('clear-files-btn');
const uploadBtn       = document.getElementById('upload-btn');
const uploadBtnText   = document.getElementById('upload-btn-text');
const uploadSpinner   = document.getElementById('upload-spinner');
const docsList        = document.getElementById('docs-list');
const filterSubject   = document.getElementById('filter-subject');
const refreshBtn      = document.getElementById('refresh-btn');
const prevPageBtn     = document.getElementById('prev-page-btn');
const nextPageBtn     = document.getElementById('next-page-btn');
const pageInfo        = document.getElementById('page-info');
const resultModal     = document.getElementById('result-modal');
const modalBody       = document.getElementById('modal-body');
const modalCloseBtn   = document.getElementById('modal-close-btn');
const modalOkBtn      = document.getElementById('modal-ok-btn');

/* ── 文件图标映射 ──────────────────────────────────────────────── */
const EXT_ICONS = {
  pdf:'📄', docx:'📝', doc:'📝', xlsx:'📊', xls:'📊',
  csv:'📊', pptx:'📑', ppt:'📑', txt:'📃', md:'📃',
  png:'🖼', jpg:'🖼', jpeg:'🖼', gif:'🖼', bmp:'🖼', webp:'🖼',
};
function fileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  return EXT_ICONS[ext] || '📁';
}

/* ── 工具函数 ──────────────────────────────────────────────────── */
function formatSize(bytes) {
  if (bytes < 1024)       return bytes + ' B';
  if (bytes < 1048576)    return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ── 学科选项加载 ──────────────────────────────────────────────── */
async function loadSubjects() {
  try {
    const resp = await fetch(`${API_BASE}/ingest/subjects`);
    const data = await resp.json();
    subjectChips.innerHTML = '';
    filterSubject.innerHTML = '<option value="">全部学科</option>';

    data.subjects.forEach(s => {
      // 上传区 chip
      const chip = document.createElement('div');
      chip.className = 'chip';
      chip.textContent = s.name;
      chip.dataset.code = s.code;
      chip.addEventListener('click', () => selectSubject(s.code, chip));
      subjectChips.appendChild(chip);

      // 筛选下拉
      const opt = document.createElement('option');
      opt.value = s.code;
      opt.textContent = s.name;
      filterSubject.appendChild(opt);
    });
  } catch (e) {
    subjectChips.innerHTML = '<span style="color:#EF4444;font-size:13px">加载学科失败</span>';
  }
}

function selectSubject(code, chipEl) {
  selectedSubject = code;
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  chipEl.classList.add('active');
  updateUploadBtn();
}

/* ── 文件列表管理 ──────────────────────────────────────────────── */
function addFiles(newFiles) {
  // 去重（按文件名+大小），避免重复添加同一文件
  const existing = new Set(selectedFiles.map(f => f.name + f.size));
  const filtered = Array.from(newFiles).filter(f => !existing.has(f.name + f.size));
  selectedFiles.push(...filtered);
  renderFileList();
  updateUploadBtn();
}

function renderFileList() {
  if (selectedFiles.length === 0) {
    fileListSection.hidden = true;
    return;
  }
  fileListSection.hidden = false;
  fileCountLabel.textContent = `已选 ${selectedFiles.length} 个文件`;
  fileList.innerHTML = selectedFiles.map((f, i) => `
    <div class="file-item" id="file-item-${i}">
      <span class="file-icon">${fileIcon(f.name)}</span>
      <span class="file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
      <span class="file-size">${formatSize(f.size)}</span>
      <button class="file-remove" data-idx="${i}" title="移除">✕</button>
    </div>
  `).join('');

  // 移除按钮事件
  fileList.querySelectorAll('.file-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      selectedFiles.splice(parseInt(btn.dataset.idx), 1);
      renderFileList();
      updateUploadBtn();
    });
  });
}

function updateUploadBtn() {
  uploadBtn.disabled = !(selectedSubject && selectedFiles.length > 0);
}

/* ── 文件选择事件 ──────────────────────────────────────────────── */
pickFilesBtn.addEventListener('click', () => fileInput.click());
pickFolderBtn.addEventListener('click', () => folderInput.click());
fileInput.addEventListener('change', () => addFiles(fileInput.files));
folderInput.addEventListener('change', () => addFiles(folderInput.files));
clearFilesBtn.addEventListener('click', () => {
  selectedFiles = [];
  fileInput.value = '';
  folderInput.value = '';
  renderFileList();
  updateUploadBtn();
});

/* ── 拖拽事件 ──────────────────────────────────────────────────── */
dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('dragover'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('dragover');

  // 支持拖入文件夹（DataTransferItemList API）
  const items = e.dataTransfer.items;
  if (items) {
    const filePromises = [];
    for (const item of items) {
      const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
      if (entry) filePromises.push(readEntry(entry));
    }
    Promise.all(filePromises).then(fileLists => {
      const all = fileLists.flat();
      if (all.length) addFiles(all);
    });
  } else {
    addFiles(e.dataTransfer.files);
  }
});

/** 递归读取 FileSystemEntry（支持子文件夹）。 */
function readEntry(entry) {
  if (entry.isFile) {
    return new Promise(resolve => entry.file(f => resolve([f])));
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    return new Promise(resolve => {
      const results = [];
      function readBatch() {
        reader.readEntries(async entries => {
          if (!entries.length) return resolve(results.flat());
          const subs = await Promise.all(entries.map(readEntry));
          results.push(...subs);
          readBatch(); // 继续读（readEntries 每次最多返回 100 条）
        });
      }
      readBatch();
    });
  }
  return Promise.resolve([]);
}

/* ── 上传入库 ──────────────────────────────────────────────────── */
uploadBtn.addEventListener('click', async () => {
  if (!selectedSubject) return;
  if (selectedFiles.length === 0) return;

  // 进入上传状态
  uploadBtn.disabled = true;
  uploadBtnText.textContent = '上传中…';
  uploadSpinner.hidden = false;

  // 更新文件行状态为"上传中"
  fileList.querySelectorAll('.file-remove').forEach(b => b.remove());

  const form = new FormData();
  form.append('subject', selectedSubject);

  // 获取选中学科的中文名
  const activeChip = subjectChips.querySelector('.chip.active');
  if (activeChip) form.append('subject_name', activeChip.textContent);

  selectedFiles.forEach(f => form.append('files', f));

  try {
    const resp = await fetch(`${API_BASE}/ingest/upload`, { method: 'POST', body: form });
    const data = await resp.json();

    if (!resp.ok) {
      showErrorModal(data.detail || `上传失败 (HTTP ${resp.status})`);
      return;
    }

    showResultModal(data);
    // 清空已选文件
    selectedFiles = [];
    fileInput.value = '';
    folderInput.value = '';
    renderFileList();
    loadDocuments();  // 刷新文档列表
  } catch (e) {
    showErrorModal('网络错误，请检查服务是否启动：' + e.message);
  } finally {
    uploadBtn.disabled = false;
    uploadBtnText.textContent = '上传并入库';
    uploadSpinner.hidden = true;
    updateUploadBtn();
  }
});

/* ── 结果弹窗 ──────────────────────────────────────────────────── */
function showResultModal(data) {
  const s = data.summary;
  modalBody.innerHTML = `
    <div class="result-summary">
      <div class="result-card result-card--total">
        <div class="result-card-num">${s.total}</div>
        <div class="result-card-label">总计</div>
      </div>
      <div class="result-card result-card--ok">
        <div class="result-card-num">${s.ok}</div>
        <div class="result-card-label">成功</div>
      </div>
      <div class="result-card result-card--skipped">
        <div class="result-card-num">${s.skipped}</div>
        <div class="result-card-label">跳过</div>
      </div>
      <div class="result-card result-card--error">
        <div class="result-card-num">${s.error}</div>
        <div class="result-card-label">失败</div>
      </div>
    </div>
    <table class="result-table">
      <thead>
        <tr>
          <th>文件名</th>
          <th>状态</th>
          <th>父块</th>
          <th>子块</th>
          <th>说明</th>
        </tr>
      </thead>
      <tbody>
        ${data.results.map(r => `
          <tr>
            <td>${escapeHtml(r.file)}</td>
            <td><span class="file-status file-status--${r.status}">${
              {ok:'成功', skipped:'跳过', error:'失败'}[r.status] || r.status
            }</span></td>
            <td>${r.parent_count}</td>
            <td>${r.child_count}</td>
            <td style="color:var(--text-muted);font-size:12px">${escapeHtml(r.message)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
  resultModal.hidden = false;
}

function showErrorModal(msg) {
  modalBody.innerHTML = `<div style="color:#DC2626;padding:12px 0">${escapeHtml(msg)}</div>`;
  resultModal.hidden = false;
}

modalCloseBtn.addEventListener('click', () => { resultModal.hidden = true; });
modalOkBtn.addEventListener('click', () => { resultModal.hidden = true; });
resultModal.addEventListener('click', e => { if (e.target === resultModal) resultModal.hidden = true; });

/* ── 已入库文档列表 ────────────────────────────────────────────── */
const SUBJECT_NAMES = { ai:'人工智能', java:'Java开发', test:'软件测试', ops:'运维', bigdata:'大数据' };

async function loadDocuments() {
  const subject = filterSubject.value;
  const offset = (currentPage - 1) * PAGE_SIZE;
  const params = new URLSearchParams({ page: currentPage, page_size: PAGE_SIZE });
  if (subject) params.append('subject', subject);

  docsList.innerHTML = '<div class="docs-empty">加载中…</div>';
  try {
    const resp = await fetch(`${API_BASE}/ingest/documents?${params}`);
    const data = await resp.json();
    totalDocs = data.total;
    renderDocuments(data.documents);
    updatePagination();
  } catch (e) {
    docsList.innerHTML = '<div class="docs-empty" style="color:#EF4444">加载失败</div>';
  }
}

function renderDocuments(docs) {
  if (!docs.length) {
    docsList.innerHTML = '<div class="docs-empty">暂无入库文档</div>';
    return;
  }
  docsList.innerHTML = docs.map(d => `
    <div class="doc-row">
      <span class="doc-icon">${fileIcon(d.filename)}</span>
      <div class="doc-info">
        <div class="doc-name" title="${escapeHtml(d.filename)}">${escapeHtml(d.filename)}</div>
        <div class="doc-meta">${d.created_at.slice(0, 16).replace('T', ' ')}</div>
      </div>
      <span class="doc-subject-tag">${SUBJECT_NAMES[d.subject] || d.subject}</span>
      <div class="doc-chunks">
        <div>${d.chunk_count} 父块</div>
        <div style="color:#9CA3AF">${(d.char_count / 1000).toFixed(1)}K 字</div>
      </div>
    </div>
  `).join('');
}

function updatePagination() {
  const totalPages = Math.max(1, Math.ceil(totalDocs / PAGE_SIZE));
  pageInfo.textContent = `第 ${currentPage} / ${totalPages} 页 · 共 ${totalDocs} 条`;
  prevPageBtn.disabled = currentPage <= 1;
  nextPageBtn.disabled = currentPage >= totalPages;
}

prevPageBtn.addEventListener('click', () => { currentPage--; loadDocuments(); });
nextPageBtn.addEventListener('click', () => { currentPage++; loadDocuments(); });
refreshBtn.addEventListener('click', () => { currentPage = 1; loadDocuments(); });
filterSubject.addEventListener('change', () => { currentPage = 1; loadDocuments(); });

/* ── 初始化 ────────────────────────────────────────────────────── */
loadSubjects();
loadDocuments();
