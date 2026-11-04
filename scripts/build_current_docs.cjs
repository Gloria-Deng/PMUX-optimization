#!/usr/bin/env node
'use strict';

// Create the technical document from the explicitly selected results.
// Example: node scripts/build_current_docs.cjs --assessment results/current_nine
//   --efficiency results/current_efficiency --out docs/current.docx
// Resolve docx through NODE_PATH or --docx-module <installed docx directory>.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const CASES = [
  ['test1', 'test1'], ['test2', 'test2'], ['test3', 'test3'], ['test4', 'test4'],
  ['pmux_case01_balanced', 'balanced'], ['pmux_case02_pipeline', 'pipeline'],
  ['pmux_case03_crossbar', 'crossbar'], ['pmux_case04_feedback', 'feedback'],
  ['pmux_case05_nested', 'nested'],
];
const WIDTH = 9706;

function csv(file) {
  const source = fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
  const records = [];
  let row = [], value = '', quoted = false, closed = false;
  for (let index = 0; index < source.length; index++) {
    const char = source[index];
    if (quoted) {
      if (char === '"') {
        if (source[index + 1] === '"') { value += '"'; index++; }
        else { quoted = false; closed = true; }
      } else value += char;
    } else if (char === '"') {
      if (value || closed) throw new Error(`CSV引号位置错误：${file}`);
      quoted = true;
    } else if (char === ',' || char === '\n' || char === '\r') {
      row.push(value); value = ''; closed = false;
      if (char !== ',') {
        if (char === '\r' && source[index + 1] === '\n') index++;
        if (row.some(item => item !== '')) records.push(row);
        row = [];
      }
    } else {
      if (closed) throw new Error(`CSV引号后存在额外文字：${file}`);
      value += char;
    }
  }
  if (quoted) throw new Error(`CSV引号未结束：${file}`);
  if (value || row.length || closed) { row.push(value); records.push(row); }
  const headers = records.shift();
  if (!headers || new Set(headers).size !== headers.length) throw new Error(`CSV列名为空或重复：${file}`);
  return records.map(items => {
    if (items.length !== headers.length) throw new Error(`CSV每行列数不同：${file}`);
    return Object.fromEntries(headers.map((name, index) => [name, items[index]]));
  });
}

function number(value, label, positive = false) {
  const parsed = Number(value);
  if (value === undefined || value === '' || !Number.isFinite(parsed) || (positive && parsed <= 0)) {
    throw new Error(`数值无效：${label}`);
  }
  return parsed;
}

function integer(value, label) {
  const parsed = number(value, label);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error(`计数无效：${label}`);
  return parsed;
}

function same(left, right, label) {
  if (Math.abs(left - right) > 1e-8 * Math.max(1, Math.abs(left), Math.abs(right))) {
    throw new Error(`计算结果不一致：${label}`);
  }
}

function uniqueCases(rows, label) {
  const mapped = new Map(rows.map(row => [row.case, row]));
  if (rows.length !== CASES.length || mapped.size !== CASES.length || CASES.some(([name]) => !mapped.has(name))) {
    throw new Error(`${label}需要九个不同的官方用例`);
  }
  return mapped;
}

function loadResults(assessment, efficiency) {
  const resources = uniqueCases(csv(path.join(assessment, 'resources.csv')), '资源表');
  const metrics = csv(path.join(assessment, 'metrics.csv'));
  const formal = csv(path.join(assessment, 'formal.csv'));
  const pairs = new Map(metrics.map(row => [`${row.case}/${row.version}`, row]));
  const checked = new Map(formal.map(row => [`${row.case}/${row.version}`, row]));
  if (metrics.length !== 18 || pairs.size !== 18 || formal.length !== 18 || checked.size !== 18) {
    throw new Error('需要九例两版的18项综合和18项EQY结果');
  }
  const timing = uniqueCases(csv(path.join(efficiency, 'summary.csv')), '效率表');
  const conditions = Object.fromEntries(fs.readFileSync(path.join(efficiency, 'conditions.txt'), 'utf8')
    .replace(/^\uFEFF/, '').split(/\r?\n/).filter(line => line.includes('='))
    .map(line => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]));
  if (!conditions.completed || !Number.isFinite(Date.parse(conditions.completed))) throw new Error('效率测试尚未完成');
  if (conditions.official_clarification !== '2026-10-31_to_11-02_items_58_to_65'
      || conditions.scored_metrics !== 'elapsed,memory' || conditions.warmup_stock_total !== '10'
      || conditions.warmup_case !== 'pmux_case05_nested' || conditions.warmup_version !== 'stock_only'
      || conditions.recheck !== '5_additional_pairs_excluding_initial') {
    throw new Error('效率结果未采用11月2日更新的第58—65条要求');
  }
  const readings = csv(path.join(efficiency, 'readings.csv'));
  const counts = { warmup: 0, initial: 0, recheck: 0 };
  for (const row of readings) {
    if (!(row.stage in counts)) throw new Error('效率读数包含未知步骤');
    if (row.stage === 'warmup' && (row.case !== 'pmux_case05_nested' || row.version !== 'stock')) {
      throw new Error('预热应仅采用原版pmux_case05_nested');
    }
    counts[row.stage]++;
  }
  if (counts.warmup !== 10 || counts.initial !== 18) throw new Error('预热或初测次数不正确');
  const cases = CASES.map(([name, short]) => {
    const resource = resources.get(name), time = timing.get(name);
    const before = integer(resource.logic_before, name), after = integer(resource.logic_after, name);
    if (before <= 0) throw new Error('原版逻辑单元须为正数');
    const reduction = 100 * (before - after) / before;
    same(reduction, number(resource.reduction_pct, name), name);
    const dff = {}, io = {};
    for (const version of ['stock', 'delivered']) {
      const measurement = pairs.get(`${name}/${version}`), result = checked.get(`${name}/${version}`);
      if (!measurement || !result || measurement.exit !== '0' || result.exit !== '0' || result.verdict !== 'PROVEN') {
        throw new Error(`综合或EQY尚未通过：${name}/${version}`);
      }
      const logic = integer(measurement.lut, name) + integer(measurement.not, name);
      same(logic, version === 'stock' ? before : after, name);
      dff[version] = integer(measurement.dff, name);
      io[version] = integer(measurement.io_bits, name);
    }
    const limits = {};
    for (const [kind, values, column] of [['dff', dff, 'dff'], ['io', io, 'io_bits']]) {
      same(integer(resource[`${column}_before`], name), values.stock, name);
      same(integer(resource[`${column}_after`], name), values.delivered, name);
      const growth = values.stock ? 100 * (values.delivered / values.stock - 1)
        : values.delivered ? null : 0;
      const overLimit = values.delivered * 100 > values.stock * 120;
      if (resource[`${kind}_over_limit`] !== String(overLimit ? 'True' : 'False')) {
        throw new Error(`DFF或IO的20%比较与原值不同：${name}/${kind}`);
      }
      if (growth !== null) same(growth, number(resource[`${kind}_growth_pct`], name), name);
      if (overLimit) throw new Error(`DFF或IO相对原版增加超过20%：${name}/${kind}`);
      limits[kind] = { growth, overLimit };
    }
    same(integer(time.logic_before, name), before, name);
    same(integer(time.logic_after, name), after, name);
    const values = {};
    for (const kind of ['elapsed', 'cpu', 'memory']) {
      values[`${kind}Before`] = number(time[`${kind}_before`], name, true);
      values[`${kind}After`] = number(time[`${kind}_after`], name, true);
      values[`${kind}Pct`] = 100 * (values[`${kind}After`] / values[`${kind}Before`] - 1);
      same(values[`${kind}Pct`], number(time[`${kind}_pct`], name), name);
    }
    const selectedCount = integer(time.selected_count, name);
    if (!['initial', 'recheck'].includes(time.selected_stage)
        || selectedCount !== (time.selected_stage === 'recheck' ? 5 : 1)) throw new Error('效率采用次数不正确');
    return { name, short, before, after, reduction, dff, io, limits, selectedCount, ...values };
  });
  const repeated = cases.filter(item => item.selectedCount === 5).length;
  if (counts.recheck !== repeated * 10) throw new Error('复测次数与汇总不同');
  return { cases, conditions, counts, mean: cases.reduce((sum, item) => sum + item.reduction, 0) / cases.length,
    elapsedWorst: Math.max(...cases.map(item => item.elapsedPct)),
    memoryWorst: Math.max(...cases.map(item => item.memoryPct)), total: readings.length };
}

function loadAdditionalChecks(options, assessment) {
  const definitions = [
    ['--parameters', '参数、位宽与共享路径检查', 'programs.txt'],
    ['--algorithm-checks', '初值与嵌套算法检查', 'program.txt'],
    ['--generality', '通用结构与限制条件检查', 'program.txt'],
    ['--command-checks', '独立命令检查', 'program.txt'],
    ['--mapped-checks', '最终Cyclone IV网表检查', 'programs.txt'],
  ];
  if (!definitions.some(([argument]) => options[argument])) return [];
  const inputs = csv(path.join(assessment, 'inputs.csv'));
  const root = path.resolve(__dirname, '..');
  const programs = {};
  for (const [version, relative] of [['stock', 'binary/baseline/yosys.exe'], ['delivered', 'binary/yosys.exe']]) {
    const records = inputs.filter(row => row.file.replace(/\\/g, '/') === relative);
    if (records.length !== 1) throw new Error(`缺少当前程序的唯一记录：${version}`);
    const current = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, relative))).digest('hex');
    if (records[0].digest !== current) throw new Error(`九例结果与当前程序不一致：${version}`);
    programs[version] = current;
  }
  return definitions.filter(([argument]) => options[argument]).map(([argument, label, programFile]) => {
    const directory = path.resolve(options[argument]);
    const checks = csv(path.join(directory, 'formal.csv'));
    const keys = checks.map(row => `${row.case}/${row.version || ''}`);
    if (!checks.length || keys.some(key => key.startsWith('undefined/')) || new Set(keys).size !== checks.length
        || checks.some(row => {
          if (argument === '--command-checks') return row.passed !== 'True'
            || !['PROVEN', 'REJECTED_AS_EXPECTED'].includes(row.verdict);
          return row.exit !== '0' || row.verdict !== 'PROVEN';
        })) {
      throw new Error(`${label}存在缺项、重复或未通过的结果`);
    }
    const program = fs.readFileSync(path.join(directory, programFile), 'utf8').replace(/^\uFEFF/, '').trim();
    if (programFile === 'program.txt') {
      if (program !== programs.delivered) throw new Error(`${label}使用了其他程序`);
    } else {
      const rows = program.split(/\r?\n/).filter(Boolean).map(line => {
        const split = line.indexOf('=');
        return [line.slice(0, split), line.slice(split + 1)];
      });
      const recorded = Object.fromEntries(rows);
      if (rows.length !== 2 || new Set(rows.map(([version]) => version)).size !== 2
          || ['stock', 'delivered'].some(version => recorded[version] !== programs[version])) {
        throw new Error(`${label}使用了其他程序或程序记录不完整`);
      }
    }
    if (argument === '--mapped-checks') {
      uniqueCases(checks, label);
      for (const row of checks) {
        if (row.version !== 'delivered') throw new Error(`${label}不是当前优化版结果`);
        const netlist = path.join(assessment, row.case, 'delivered', 'final.il');
        const current = crypto.createHash('sha256').update(fs.readFileSync(netlist)).digest('hex');
        if (row.netlist_digest !== current) throw new Error(`${label}与本次最终网表不一致：${row.case}`);
      }
    }
    return { argument, label, count: checks.length };
  });
}

function createDocument(api, data) {
  const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, Header, Footer,
    AlignmentType, HeadingLevel, WidthType, BorderStyle, ShadingType, PageNumber,
    ExternalHyperlink, TableLayoutType } = api;
  const bodyFont = { ascii: 'Calibri', hAnsi: 'Calibri', eastAsia: '宋体', cs: 'Calibri' };
  const headingFont = { ascii: 'Calibri', hAnsi: 'Calibri', eastAsia: '微软雅黑', cs: 'Calibri' };
  const p = (text, options = {}) => new Paragraph({ spacing: { after: 110, line: 310 },
    ...options, children: [new TextRun({ text, font: bodyFont, size: 22 })] });
  const title = (text, first = false) => new Paragraph({ heading: HeadingLevel.HEADING_1,
    pageBreakBefore: !first, children: [new TextRun({ text, font: headingFont, bold: true, size: 32, color: '17324D' })] });
  const h = text => new Paragraph({ heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, font: headingFont, bold: true, size: 25 })] });
  const command = text => new Paragraph({ spacing: { before: 60, after: 70, line: 260 },
    shading: { fill: 'F2F5F8', type: ShadingType.CLEAR },
    children: [new TextRun({ text, font: { ...bodyFont, ascii: 'Consolas', hAnsi: 'Consolas' }, size: 18 })] });
  const table = (headers, rows, widths) => new Table({
    width: { size: WIDTH, type: WidthType.DXA }, columnWidths: widths, layout: TableLayoutType.FIXED,
    rows: [headers, ...rows].map((row, rowIndex, all) => new TableRow({
      cantSplit: true, tableHeader: rowIndex === 0,
      children: row.map((text, index) => new TableCell({
        width: { size: widths[index], type: WidthType.DXA },
        margins: { top: 85, bottom: 85, left: 90, right: 90 },
        shading: { fill: rowIndex === 0 ? 'E5EEF5' : rowIndex % 2 === 0 ? 'F6F8FA' : 'FFFFFF', type: ShadingType.CLEAR },
        borders: Object.fromEntries(['top', 'bottom', 'left', 'right'].map(side => [side,
          { style: BorderStyle.SINGLE, size: 3, color: 'CFD8E0' }])),
        children: [new Paragraph({ alignment: index ? AlignmentType.CENTER : AlignmentType.LEFT,
          keepNext: rowIndex < all.length - 1, spacing: { after: 0, line: 240 },
          children: [new TextRun({ text: String(text), font: rowIndex === 0 ? headingFont : bodyFont,
            bold: rowIndex === 0, size: 19 })] })],
      })),
    })),
  });
  const pct = value => `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
  const growthText = value => value === null ? '原版0，优化版增加' : pct(value);
  const completed = data.conditions.completed.slice(0, 10);
  const protection = { True: '开启', False: '关闭' }[data.conditions.real_time_protection_enabled] || '未能读取';
  const passResources = data.cases.every(item => item.after <= item.before);
  const passOtherResources = data.cases.every(item => !item.limits.dff.overLimit && !item.limits.io.overLimit);
  const efficiencyClass = data.elapsedWorst <= 5 + 1e-9 && data.memoryWorst <= 5 + 1e-9
    ? '各例经过时间和内存增幅均不超过5%' : data.elapsedWorst <= 15 + 1e-9 && data.memoryWorst <= 15 + 1e-9
      ? '至少一项超过5%，各例两项均不超过15%' : '至少一例的经过时间或内存增幅超过15%';
  const repeated = data.cases.filter(item => item.selectedCount === 5).map(item => item.short).join('、') || '无';
  const extra = data.additionalChecks || [];
  const coverage = [
    extra.some(item => item.argument === '--generality')
      ? '通用结构检查覆盖优先链位重排与外部读取、宽比较的共同0位和关闭选项、浅层共享及限制条件。' : '',
    extra.some(item => item.argument === '--command-checks')
      ? '独立命令四项检查包含两项EQY和两项禁止选项的拒绝检查，确认无额外ABC执行。' : '',
    extra.some(item => item.argument === '--mapped-checks')
      ? '最终网表检查另行比较完成器件映射后的九例与原始RTL。' : '',
  ].join('');
  const pages = [
    [title('第一部分 作品概述', true),
      p('PMUX 结构优化器', { alignment: AlignmentType.CENTER, spacing: { before: 150, after: 180 } }),
      p(`技术说明 · 结果完成日期 ${completed} · 官方答复更新至2026年11月2日`, { alignment: AlignmentType.CENTER }),
      h('功能与应用'),
      p('作品在Windows版Yosys主程序内加入pmux_opt_rtlil，由synth_intel在proc之后调用。输入为Verilog，输出为Cyclone IV网表，面向条件选择、流水数据通路、交叉选择及寄存器反馈电路。'),
      h('核心算法'),
      p('程序按电路结构合并重复选择路径，共享符合位宽、符号及使用范围要求的运算。新增宽于4位的相等比较共享：对共同取0的比较位先取反，再共用一致条件；显式关闭比较共享时不执行该规则。'),
      p('互斥加减共享扩展到两层独立选择。沿完整路径选择操作数，同树内适用表达式共用加减单元；仅接受相同完整位宽，保留减法方向与结果截位。'),
      command('mux(op(a0,b0), op(a1,b1), s) → op(mux(a0,a1,s), mux(b0,b1,s))'),
      p('优先选择链修复两类问题：前级结果须按原位序完整连接，避免把位重排当成直连；统计全部输入及模块输出的使用，避免漏掉D端等读取。外部复用、循环依赖或要求保留的结构限制变换。'),
      h('本版范围与结果'),
      p('全部新增规则在ABC9之前执行。官方九例输入、默认参数和原ABC9映射命令保持不变；不按用例名或信号名选择规则。有限用例的收益不能推出所有电路都会缩减。'),
      p(`九例平均逻辑单元缩减率为${data.mean.toFixed(6)}%；${passResources ? '各例逻辑单元均未增加' : '存在逻辑单元增加的用例'}。${passOtherResources ? '各例DFF和IO增幅均不超过20%。' : '存在DFF或IO增幅超过20%的用例。'}九例两版共18项EQY通过。效率结果为：${efficiencyClass}。详见资源、功能与效率部分。`),
    ],
    [title('第二部分 系统组成及功能说明'),
      h('综合流程与检查位置'),
      command('Verilog → hierarchy / proc / 零初始化 → PMUX优化 → 原有优化 → ABC9 → Cyclone IV网表'),
      table(['组成', '处理与输出'], [
        ['输入与结构转换', '读取九例默认参数，proc将进程转换为内部电路'],
        ['PMUX优化', '分析选择条件，合并重复数据路径，共享适用运算'],
        ['原有综合与ABC9', '沿用所选源码流程和脚本，不增加组合优化策略'],
        ['资源统计', '输出网表之后统计LUT与取反单元；DFF另列'],
        ['功能检查', '原始RTL与ABC9之后、map_cells之前的逻辑网表比较'],
        ['效率测量', '同一次综合取得经过时间与主程序峰值工作集'],
      ], [2300, 7406]),
      h('状态、复位与适用边界'),
      p('按第54条，两版综合前将未指定的寄存器初值补零，保留明确初值，准备时间计入效率。EQY比较本次实际输出，同时检查寄存器模型、初值和控制连接。'),
      p('寄存器控制转换读取明确的0/1初值及相连名称；反向保存时同步取反，随后写入新寄存器的power_up参数。转换保持时钟、复位、使能与状态行为。'),
      p('普通运算共享匹配类型与参数；两层及更深的嵌套规则允许同宽加减混合。共享结果须只供受支持的选择路径使用。部分位、拼接、额外表达式或控制条件依赖待共享结果时保留原结构；每次修改后重新读取电路关系。'),
      p('多驱动、不支持的控制、宽度不一致及保留属性均会限制变换。路径数量和深度设上限；比较共享的共同0位与共同1位分别按取反后及直接输入构造条件。'),
      h('软硬件组成'),
      p('本作品为软件交付，不需要板卡、eLinx工程或硬件仿真报告。正式评测采用原四例与新增五例，不调整默认LANES、WIDTH参数；额外电路仅用于检查规则适用范围。'),
      h('允许的修改范围'),
      p('第59、63、65条允许修改统一ABC脚本和新增优化pass，禁止修改其他pass的实现、重排原有调用顺序或额外多次调用ABC。本版在原有proc之后插入新增pass，保留其他步骤的顺序及原版ABC9命令；新增规则内部不执行额外ABC试算。全部优化计算计入完整综合时间。'),
    ],
    [title('第三部分 运行与重新构建'),
      h('版本与共同运行条件'),
      p('第58、59、62条要求Yosys大版本为0.69，允许自行选择具体公开提交，不允许0.70；ABC应对应采用的Yosys版本。本版两份程序均从公开d0e71cfb7对应源码构建，版本为0.69+24；ABC对应1e3d9ab。两版同时应用a697ccbbc中的Windows二进制输出修正，以同一运行库、技术库、ABC和测量工具执行同一脚本。'),
      h('Windows检查入口'),
      p('在工程根目录运行下列命令，输出目录应为新目录。按第60、65条，赛事方准备并调试OSS CAD Suite验证环境；运行时将实际安装位置写入OSS_CAD_SUITE环境变量。缺少make、sh或grep时，通过PMUX_MAKE_DIRS指定辅助程序目录。'),
      command('$env:OSS_CAD_SUITE = "<OSS CAD Suite安装目录>"'),
      command('$env:PMUX_MAKE_DIRS = "<MSYS2安装目录>/usr/bin"'),
      command('./scripts/run_python.cmd scripts/evaluate_official_nine.py `'),
      command('  --out results/new_nine --phase all'),
      command('./scripts/run_python.cmd scripts/measure_official_efficiency.py `'),
      command('  --assessment results/new_nine `'),
      command('  --out results/new_efficiency'),
      p('综合命令通过-s导入脚本。脚本读取用例，运行synth_intel -family cycloneiv -top <顶层>，再输出网表并统计单元。功能检查另行执行，其时间不计入效率。'),
      command('./binary/yosys.exe -s <综合脚本.ys>'),
      h('重新编译'),
      p('需要与当前版本一致、已配置且保留对象文件的Yosys构建目录。编译入口读取其编译设置和已有对象，将当前PMUX源码与综合流程源码编译到新位置，不改动原构建目录。'),
      command('python scripts/build_general_candidate.py `'),
      command('  --build-dir <构建目录> --source plugin/pmux_opt_rtlil.cc `'),
      command('  --synth-intel-source plugin/synth_intel.cc.patched `'),
      command('  --out <新目录>/yosys.exe'),
      p('从零重建还需对应Yosys和ABC源码及Windows编译环境。Yosys编译时间不参与效率评分。使用已交付程序时，无需重新编译。'),
    ],
    [title('第四部分 九例资源结果'),
      h('九例资源结果'),
      p('逻辑单元数为LUT加取反单元，DFF和IO分别计数。平均缩减率取九例逐例缩减率的算术平均值，不能用全部单元合计后的缩减率代替。'),
      table(['用例', '原版逻辑', '优化逻辑', '缩减率'],
        data.cases.map(item => [item.short, item.before, item.after, `${item.reduction.toFixed(2)}%`]),
        [2500, 2400, 2400, 2406]),
      p(`九例平均缩减率：${data.mean.toFixed(9)}%。${passResources ? '各例逻辑单元未增加。' : '部分用例逻辑单元增加，不能宣称满足逐例不增加要求。'}`,
        { spacing: { before: 180, after: 110, line: 310 } }),
      p(data.mean >= 20 ? '平均缩减达到面积项20%的满分数值要求。' : data.mean >= 10 ? '平均缩减满足赛题10%的面积要求，尚未达到面积项20%的满分线。' : '平均缩减未达到赛题10%的面积要求。'),
      h('DFF与IO比较'),
      table(['用例', '原版DFF', '优化DFF', 'DFF增幅', '原版IO位', '优化IO位', 'IO增幅'],
        data.cases.map(item => [item.short, item.dff.stock, item.dff.delivered, growthText(item.limits.dff.growth),
          item.io.stock, item.io.delivered, growthText(item.limits.io.growth)]),
        [1700, 1200, 1200, 1400, 1400, 1400, 1406]),
      p('第63条要求DFF或IO相对原版增加超过20%会影响评分。本工程按逐例增幅检查，IO采用最终网表顶层输入、输出和双向端口的位数；Cyclone IV流程未插入独立IO器件单元，因此不把IO端口计入LUT数量。原版为0、优化版仍为0记作0%；原版为0而优化版新增则列为超出20%。'),
      p(passOtherResources ? '本组九例DFF及IO均未超出20%的增幅限制。' : '本组存在DFF或IO增幅超出20%的用例。'),
    ],
    [title('第五部分 功能验证与适用范围'),
      h('功能与适用范围检查'),
      p('九例两版分别与原始RTL比较，18项EQY均为PROVEN并返回成功。按官方第18条，正式比较位置为ABC9之后、Cyclone IV映射之前。'),
      p((data.additionalChecks || []).length ? data.additionalChecks.map(item => `${item.label}${item.count}项全部通过`).join('；') + '。' : '未指定额外检查结果，不计入其他版本的完成项。'),
      p(`${coverage}额外结果不计入九例平均值。`),
      p('资源与正式功能结果取自同一九例目录；补充结果核对当前程序，最终映射结果另核对两版程序和本次网表。EQY比较仅接受PROVEN且返回成功的结果；禁止选项须按预期拒绝。'),
      h('初值与未知值处理'),
      p('第63、64条明确X/Z按0初始化，验证方法由参赛队决定。本工程在两版综合前使用相同脚本：原始RTL转换为寄存器结构后补全未指定的零初值，明确初值保留。验证读取本次ABC9之后的实际RTLIL，保留变换生成的内部初值，避免把反相保存位等内部状态重新全部置零。输入、时钟和复位不增加额外限制。'),
      h('验证材料'),
      p('第63条要求提交EQY验证脚本。工程提供EQY调用入口、验证配置生成代码、寄存器功能模型和本次结果；验证工具使用外部OSS CAD Suite。形式验证时间不参与综合效率比较。'),
      h('适用限制'),
      p('第51条说明正式评测不测九例之外的电路；第45条仍要求通用优化、逐例逻辑单元不增加。本程序按位宽、完整连接、互斥关系和读取范围识别结构，不按用例名选择规则；遇到不满足条件的结构保留原逻辑。额外检查用于发现不适用情形，不能由有限通过项目推断任意电路均等价或都会缩减。'),
      p('依据最新整理的第59、63、65条，不要求提交自定义规则的独立收益消融，也没有规定独立收益最低占比。本报告展示完整程序在统一流程下的实际结果。'),
    ],
    [title('第六部分 效率测量与结果'),
      p('评分只采用完整经过时间与Yosys主程序峰值工作集。CPU时间保留参考，既不影响评分，也不触发复测。时间覆盖程序创建至输出收集完成，包含ABC运行与网表输出。'),
      table(['用例', '原版秒', '优化秒', '时间增幅', '原版MiB', '优化MiB', '内存增幅', 'CPU增幅参考'],
        data.cases.map(item => [item.short, item.elapsedBefore.toFixed(4), item.elapsedAfter.toFixed(4), pct(item.elapsedPct),
          item.memoryBefore.toFixed(2), item.memoryAfter.toFixed(2), pct(item.memoryPct), pct(item.cpuPct)]),
        [1300, 1200, 1200, 1100, 1200, 1200, 1100, 1406]),
      p(`经过时间最高增幅${pct(data.elapsedWorst)}，峰值工作集最高增幅${pct(data.memoryWorst)}；${efficiencyClass}。`,
        { spacing: { before: 150, after: 90, line: 300 } }),
      h('执行顺序与采用次数'),
      p('按第61、63条，测试开始仅用原版pmux_case05_nested连续预热10次；系统重启后重新预热。随后每例先原版、后优化版。初测中两版较长时间不足10秒，且经过时间或内存增幅超过5%，则追加五对并分别求平均；达到10秒只采用初测。'),
      p('本工程固定采用追加五对且排除初测的方式；原始初测保留供检查。两版分别对原值求平均，再计算相对增幅，不对每对百分比求平均，也不挑选最好结果。后台程序保持统一，正式测量要求关闭安全软件；下列状态反映本次实际条件。'),
      p(`共${data.total}次综合：预热${data.counts.warmup}次、初测${data.counts.initial}次、追加复测${data.counts.recheck}次。采用五次平均值的用例：${repeated}；其余采用每版一次初测。Microsoft Defender实时保护状态为${protection}。`),
    ],
    [title('第七部分 交付说明与参考资料'),
      h('交付内容'),
      p('官方要求代码为RAR且小于200MB、设计报告为PDF且小于50MB。工程提供当前优化源码、两版Yosys与运行依赖、九个用例、综合入口、EQY验证脚本、当前结果和技术文档。OSS CAD Suite由赛事方准备，不随工程附带。本次按用户要求不生成压缩包。'),
      p('现有视频保持原文件，待用户按最终程序与数值另行制作；本次不修改或打包视频。官方要求MP4、AVC/H.264，建议3分钟及300MB以内，不出现学校、指导老师等无关信息。'),
      h('已完成与待确认'),
      p(`本次指定结果包含九例两版资源统计、18项通过的EQY，以及按11月2日第58—65条更新完成的效率测试。平均逻辑单元缩减${data.mean.toFixed(6)}%；${efficiencyClass}。`),
      p('待确认事项：作品上传页面的设计报告模板未包含在给定四份材料中，尚缺其章节、版式和必填内容；现场OSS CAD Suite实际版本、安装路径与辅助程序位置尚未提供。照片、授权书、GitHub链接和海报按上传页面及企业要求准备。若本次实时保护状态为开启，正式测量仍需按官方要求关闭安全软件并统一后台条件后完成。'),
      h('参考资料'),
      p('[1] 中科亿海微：优先级最高_saiti_extract.txt，选题二功能、面积、性能和文档要求。'),
      p('[2] 中科亿海微：优先级最高_官方解答.txt，2026年11月3日同步，2026年10月31日—11月2日第58—65条；FPGA创新大赛问题汇总.xlsx，Sheet1第161—168行。计数及功能要求同时采用第18、21、45条。'),
      p('[3] 中科亿海微：官方要求.txt，作品上传格式、大小和报告模板说明；原材料记载截止时间为2026年11月4日18:00。'),
      new Paragraph({ spacing: { after: 100, line: 260 }, children: [new TextRun({ text: '[4] YosysHQ：Yosys公开源码 d0e71cfb7。', font: bodyFont, size: 20 }),
        new ExternalHyperlink({ link: 'https://github.com/YosysHQ/yosys/tree/d0e71cfb7', children: [new TextRun({ text: '源码链接', style: 'Hyperlink', size: 20 })] })] }),
      new Paragraph({ spacing: { after: 100, line: 260 }, children: [new TextRun({ text: '[5] YosysHQ：Windows二进制输出修正 a697ccbbc。', font: bodyFont, size: 20 }),
        new ExternalHyperlink({ link: 'https://github.com/YosysHQ/yosys/commit/a697ccbbc', children: [new TextRun({ text: '修正链接', style: 'Hyperlink', size: 20 })] })] }),
      new Paragraph({ spacing: { after: 100, line: 260 }, children: [new TextRun({ text: '[6] YosysHQ：EQY官方说明。', font: bodyFont, size: 20 }),
        new ExternalHyperlink({ link: 'https://yosyshq.readthedocs.io/projects/eqy/en/latest/', children: [new TextRun({ text: '使用说明', style: 'Hyperlink', size: 20 })] })] }),
    ],
  ];
  const doc = new Document({ creator: 'PMUX项目组', title: 'PMUX结构优化技术文档', description: '依据当前九例资源、功能和效率结果生成',
    styles: {
      default: { document: { run: { font: bodyFont, size: 22 }, paragraph: { spacing: { after: 110, line: 310 } } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { font: headingFont, size: 32, bold: true },
          paragraph: { outlineLevel: 0, keepNext: true, spacing: { before: 0, after: 220 } } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { font: headingFont, size: 25, bold: true },
          paragraph: { outlineLevel: 1, keepNext: true, spacing: { before: 170, after: 100 } } },
      ],
    },
    sections: [{
      properties: { page: { size: { width: 11906, height: 16838 },
        margin: { top: 1080, bottom: 1000, left: 1100, right: 1100, header: 500, footer: 500 } } },
      headers: { default: new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 5, color: '9BAFC1', space: 4 } },
        children: [new TextRun({ text: 'PMUX结构优化器  |  技术文档', font: headingFont, size: 18, color: '60758A' })],
      })] }) },
      footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: '第 ', font: bodyFont, size: 18 }),
          new TextRun({ children: [PageNumber.CURRENT], size: 18 }),
          new TextRun({ text: ' 页 / 共 ', font: bodyFont, size: 18 }),
          new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 18 }), new TextRun({ text: ' 页', font: bodyFont, size: 18 })],
      })] }) },
      children: pages.flat(),
    }],
  });
  return Packer.toBuffer(doc);
}

async function main(argv) {
  if (argv.includes('--help')) {
    console.log('用法：node build_current_docs.cjs --assessment <九例结果目录> --efficiency <效率目录> --out <新文件.docx> [--parameters <参数检查目录>] [--algorithm-checks <算法检查目录>] [--generality <通用结构检查目录>] [--command-checks <独立命令目录>] [--mapped-checks <最终网表检查目录>] [--docx-module <docx模块目录>]');
    return;
  }
  const options = {};
  for (let index = 0; index < argv.length; index += 2) {
    if (!['--assessment', '--efficiency', '--out', '--docx-module', '--parameters', '--algorithm-checks', '--generality', '--command-checks', '--mapped-checks'].includes(argv[index]) || !argv[index + 1]
        || argv[index + 1].startsWith('--')) throw new Error(`参数不正确：${argv[index]}`);
    if (options[argv[index]]) throw new Error(`参数重复：${argv[index]}`);
    options[argv[index]] = argv[index + 1];
  }
  for (const required of ['--assessment', '--efficiency', '--out']) {
    if (!options[required]) throw new Error(`缺少参数：${required}`);
  }
  const output = path.resolve(options['--out']);
  if (path.extname(output).toLowerCase() !== '.docx') throw new Error('输出文件应以.docx结尾');
  if (fs.existsSync(output)) throw new Error('输出已存在，请使用新的文件名');
  const data = loadResults(path.resolve(options['--assessment']), path.resolve(options['--efficiency']));
  data.additionalChecks = loadAdditionalChecks(options, path.resolve(options['--assessment']));
  const api = options['--docx-module'] ? require(path.resolve(options['--docx-module'])) : require('docx');
  const buffer = await createDocument(api, data);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, buffer, { flag: 'wx' });
  console.log(`已生成技术文档：${output}；九例平均缩减${data.mean.toFixed(6)}%，18项EQY通过，效率综合${data.total}次。`);
}

if (require.main === module) main(process.argv.slice(2)).catch(error => { console.error(error.message); process.exitCode = 1; });
module.exports = { csv, loadResults, loadAdditionalChecks, createDocument, main };
