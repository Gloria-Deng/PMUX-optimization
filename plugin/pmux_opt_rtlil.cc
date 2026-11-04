#include "kernel/yosys.h"
#include "kernel/rtlil.h"
#include "kernel/register.h"
#include "kernel/log.h"
#include "kernel/mem.h"
#include "kernel/ffinit.h"
#include "kernel/celltypes.h"

#include <cstring>
#include <memory>
#include <cstdlib>
#include <map>
#include <utility>
#include <vector>
#include <string>
#include <set>
#include <algorithm>
#include <cstdint>
#include <tuple>

USING_YOSYS_NAMESPACE

struct PmuxOptRtlilPass : public Pass {
	bool do_rewrite = false;
	bool naive_enabled = false;
	bool general_mux_enabled = true;


	static constexpr bool counter_enabled = false;


	bool probe_all = false;


	static constexpr bool no_probe = true;


	bool no_prio_or = false;


	bool no_decode_share = true;
	bool wide_decode_share_enabled = true;
	bool no_sclr_promo = true;


	bool sclr_promo_rom_only = false;


	bool no_hold_extract = true;


	bool preopt = false;

	PmuxOptRtlilPass() : Pass("pmux_opt_rtlil", "PMUX RTLIL inspect / bank+swap rewrite") {}

	void help() override
	{
		log("\n");
		log("    pmux_opt_rtlil [-rewrite] [-no-probe] [-sclr-promo-rom-only] [selection]\n");
		log("\n");
		log("Inspect PMUX and mux structures. With -rewrite, apply structural rules:\n");
		log("  * Merge repeated paths and dense binary data selections.\n");
		log("  * Factor swapped data banks and selector-dependent constant data.\n");
		log("  * Rewrite private priority chains with exact full-width connections.\n");
		log("  * Share compatible full-width add/sub operations on exclusive paths,\n");
		log("    including two-level and deeper selection trees.\n");
		log("  * Share common conditions in comparison pairs wider than four bits.\n");
		log("    Shared zero bits are inverted before the common condition is built.\n");
		log("\n");
		log("Structural rules never invoke ABC or run extra design syntheses.\n");
		log("-no-probe is accepted for compatibility; -probe-all and -counter are unavailable.\n");
		log("-sclr-promo-rom-only also converts eligible register controls in modules\n");
		log("with read-only memory, preserving explicit and aliased initial values.\n");
		log("\n");
		log("The synth_intel integration uses -rewrite -sclr-promo-rom-only -no-probe\n");
		log("after proc. All custom rewrites precede the unchanged ABC9 command.\n");
		log("\n");
		log("Optional controls:\n");
		log("  -no-general-mux   Disable general selection and arithmetic sharing.\n");
		log("  -no-prio-or       Disable priority-chain rewriting.\n");
		log("  -no-decode-share  Disable all comparison-condition sharing.\n");
		log("  -no-sclr-promo    Disable register-control conversion.\n");
		log("\n");
		log("Additional experimental options (not used by the delivery integration):\n");
		log("  -naive, -preopt, -decode-share, -sclr-promo,\n");
		log("  -hold-extract, -no-hold-extract. -decode-share includes comparisons\n");
		log("  narrower than five bits and can increase mapped area.\n");
		log("\n");
		log("Run after read_verilog, hierarchy and proc. Unsupported structures stay\n");
		log("unchanged; inspect the actual synthesized result for area comparisons.\n");
		log("\n");
	}

	static bool const_uint(const SigSpec &s, int &out)
	{
		if (GetSize(s) == 0 || GetSize(s) > 31)
			return false;
		if (!s.is_fully_const())
			return false;
		out = s.as_int(false);
		return true;
	}


	SigSpec mux_on(SigBit s, const SigSpec &a, const SigSpec &b, Module *mod, int &nnew)
	{
		Cell *m = mod->addCell(NEW_ID, ID($mux));
		m->setParam(ID(WIDTH), GetSize(a));
		m->setPort(ID::A, a);
		m->setPort(ID::B, b);
		m->setPort(ID::S, s);
		Wire *y = mod->addWire(NEW_ID, GetSize(a));
		m->setPort(ID::Y, y);
		nnew++;
		return y;
	}


	SigSpec build_tree(std::vector<SigSpec> &leaves, int lo, int hi, int wbit,
	                   const SigSpec &W, Module *mod, int &nnew)
	{
		if (lo + 1 >= hi)
			return leaves[lo];
		int mid = (lo + hi) / 2;
		SigSpec a = build_tree(leaves, lo, mid, wbit - 1, W, mod, nnew);
		SigSpec b = build_tree(leaves, mid, hi, wbit - 1, W, mod, nnew);
		Cell *m = mod->addCell(NEW_ID, ID($mux));
		m->setParam(ID(WIDTH), GetSize(a));
		m->setPort(ID::A, a);
		m->setPort(ID::B, b);
		m->setPort(ID::S, W[wbit]);
		Wire *y = mod->addWire(NEW_ID, GetSize(a));
		m->setPort(ID::Y, y);
		nnew++;
		return y;
	}


	SigSpec build_arms_tree(std::vector<std::pair<int, SigSpec>> arms, const SigSpec &W,
	                        int level, const SigSpec &dflt, Module *mod, int &nnew)
	{
		if (arms.empty())
			return dflt;
		if (level < 0)
			return arms[0].second;
		std::vector<std::pair<int, SigSpec>> lo, hi;
		for (auto &a : arms) {
			if ((a.first >> level) & 1)
				hi.push_back(a);
			else
				lo.push_back(a);
		}
		SigSpec l = build_arms_tree(lo, W, level - 1, dflt, mod, nnew);
		SigSpec r = build_arms_tree(hi, W, level - 1, dflt, mod, nnew);
		if (l == r)
			return l;
		Cell *m = mod->addCell(NEW_ID, ID($mux));
		m->setParam(ID(WIDTH), GetSize(l));
		m->setPort(ID::A, l);
		m->setPort(ID::B, r);
		m->setPort(ID::S, W[level]);
		Wire *y = mod->addWire(NEW_ID, GetSize(l));
		m->setPort(ID::Y, y);
		nnew++;
		return y;
	}

	struct Cand {
		Cell *c;
		SigSpec S, A, Y;
		SigSpec ref;
		int w, sw, nbits;
		std::map<int, SigSpec> arm;
		bool consumed = false;
	};


	bool collect_leaves(Cand &cd, int shift, int n_pairs, std::vector<SigSpec> &no_l,
	                    std::vector<SigSpec> &sw_l, SigSpec &start)
	{
		int half = 1 << (shift - 1);
		start = cd.arm.count(0) ? cd.arm.at(0) : cd.A;
		no_l.assign(n_pairs, SigSpec());
		sw_l.assign(n_pairs, SigSpec());
		for (int p = 0; p < n_pairs; p++) {
			for (int ph = 0; ph < 2; ph++) {
				SigSpec rep;
				for (int k = 0; k < half; k++) {
					int code = (p << shift) + ph * half + k;
					SigSpec d = cd.arm.count(code) ? cd.arm.at(code) : cd.A;
					if (code == 0)
						d = start;
					if (rep.empty())
						rep = d;
					else if (!(rep == d))
						return false;
				}
				(ph ? sw_l : no_l)[p] = rep;
			}
		}
		return true;
	}


	int rewrite_priority_or_chains(Module *mod, int &newcells, int min_len = 3)
	{

		CellTypes celltypes(mod->design);
		std::map<SigBit, Cell *> drv;
		for (Cell *c : mod->cells()) {
			if (!c->hasPort(ID::Y))
				continue;
			for (SigBit b : c->getPort(ID::Y))
				if (b.wire != nullptr)
					drv[b] = c;
		}


		std::vector<Cell *> muxes;
		for (Cell *c : mod->cells())
			if (c->type == ID($mux))
				muxes.push_back(c);
		std::map<Cell *, Cell *> next_of;
		std::map<Cell *, int> succs;
		for (Cell *m : muxes) {
			SigSpec a = m->getPort(ID::A);
			if (GetSize(a) == 0 || a[0].wire == nullptr)
				continue;
			auto it = drv.find(a[0]);
			if (it == drv.end() || it->second == m || it->second->type != ID($mux))
				continue;
			Cell *up = it->second;
			if (up->getPort(ID::Y) != a)
				continue;


			bool whole = true;
			for (int k = 1; k < GetSize(a) && whole; k++) {
				SigBit b = a[k];
				if (b.wire == nullptr) { whole = false; break; }
				auto d2 = drv.find(b);
				if (d2 == drv.end() || d2->second != up)
					whole = false;
			}
			if (!whole)
				continue;
			next_of[m] = up;
			succs[up]++;
		}


		std::vector<Cell *> roots;
		for (Cell *m : muxes) {
			if (succs.count(m))
				continue;
			if (!next_of.count(m))
				continue;
			roots.push_back(m);
		}
		int n = 0;
		for (Cell *root : roots) {

			std::vector<Cell *> chain;
			Cell *cur = root;
			bool ok = true;
			std::set<Cell *> seen;
			while (ok) {
				if (!seen.insert(cur).second) {
					ok = false;
					break;
				}
				chain.push_back(cur);
				auto it = next_of.find(cur);
				if (it == next_of.end())
					break;
				cur = it->second;
			}
			if (!ok || (int)chain.size() < min_len)
				continue;


			int w = GetSize(root->getPort(ID::Y));
			if (w <= 0)
				continue;
			for (int i = 0; i < (int)chain.size() && ok; i++) {
				Cell *m = chain[i];
				if (m->getParam(ID(WIDTH)).as_int() != w ||
				    GetSize(m->getPort(ID::B)) != w || GetSize(m->getPort(ID::S)) != 1 ||
				    GetSize(m->getPort(ID::A)) != w) {
					ok = false;
					break;
				}
				SigBit s = m->getPort(ID::S)[0];
				if (s.wire == nullptr) {
					ok = false;
					break;
				}
				auto it = drv.find(s);
				if (it != drv.end()) {
					Cell *sd = it->second;
					if (sd->type == ID($eq) || seen.count(sd)) {
						ok = false;
						break;
					}
				}
				if (i + 1 < (int)chain.size() && next_of.at(m) != chain[i + 1]) {
					ok = false;
					break;
				}
			}
			if (!ok)
				continue;
			SigSpec term = chain.back()->getPort(ID::A);
			for (int i = 0; i < (int)chain.size() && ok; i++) {
				SigSpec d = chain[i]->getPort(ID::B);
				for (int j = 0; j < w && ok; j++)
					if (d[j].wire != nullptr && seen.count(drv.count(d[j]) ? drv.at(d[j]) : nullptr))
						ok = false;
			}
			if (!ok)
				continue;


			std::map<SigBit, std::set<Cell *>> readers;
			for (Cell *c : mod->cells()) {
				for (auto &port : c->connections()) {
					if (celltypes.cell_known(c->type) && !celltypes.cell_input(c->type, port.first))
						continue;
					for (SigBit b : port.second)
						if (b.wire != nullptr)
							readers[b].insert(c);
				}
			}
			for (Wire *wire : mod->wires())
				if (wire->port_output)
					for (SigBit bit : SigSpec(wire))
						readers[bit].insert(nullptr);
			for (int i = 1; i < (int)chain.size() && ok; i++) {
				Cell *consumer = chain[i - 1];
				for (SigBit b : chain[i]->getPort(ID::Y)) {
					if (b.wire == nullptr)
						continue;
					auto r = readers.find(b);
					if (r == readers.end() || r->second.size() != 1 ||
					    !r->second.count(consumer)) {
						ok = false;
						break;
					}
				}
			}
			if (ok) {
				auto sig_has = [](const SigSpec &s, const SigBit &b) {
					for (SigBit x : s)
						if (x.wire == b.wire && x.offset == b.offset && x.data == b.data)
							return true;
					return false;
				};
				for (int i = 1; i < (int)chain.size() && ok; i++) {
					for (SigBit b : chain[i]->getPort(ID::Y)) {
						if (b.wire == nullptr)
							continue;
						for (auto &conn : mod->connections()) {
							if (sig_has(conn.first, b) || sig_has(conn.second, b)) {
								ok = false;
								break;
							}
						}
						if (!ok)
							break;
					}
				}
			}
			if (!ok)
				continue;

			std::string nm = log_id(root->name);


			SigBit en_any;
			SigSpec acc;
			for (int i = 0; i < (int)chain.size(); i++) {
				SigBit c = chain[i]->getPort(ID::S)[0];
				SigBit e;
				if (i == 0) {
					e = c;
					en_any = c;
				} else {
					Wire *ne = mod->addWire(NEW_ID, 1);
					mod->addNot(NEW_ID, en_any, ne);
					Wire *ew = mod->addWire(NEW_ID, 1);
					mod->addAnd(NEW_ID, c, ne, ew);
					e = ew;
					Wire *oa = mod->addWire(NEW_ID, 1);
					mod->addOr(NEW_ID, en_any, c, oa);
					en_any = oa;
					newcells += 3;
				}
				Cell *tm = mod->addCell(NEW_ID, ID($mux));
				tm->setParam(ID(WIDTH), w);
				tm->setPort(ID::A, SigSpec(State::S0, w));
				tm->setPort(ID::B, chain[i]->getPort(ID::B));
				tm->setPort(ID::S, e);
				Wire *tw = mod->addWire(NEW_ID, w);
				tm->setPort(ID::Y, tw);
				newcells++;
				if (i == 0) {
					acc = tw;
				} else {
					Wire *ow = mod->addWire(NEW_ID, w);
					mod->addOr(NEW_ID, acc, tw, ow);
					acc = ow;
					newcells++;
				}
			}

			SigSpec dflt = chain.back()->getPort(ID::A);
			if (!(dflt.is_fully_const() && dflt.is_fully_zero())) {
				Wire *ne = mod->addWire(NEW_ID, 1);
				mod->addNot(NEW_ID, en_any, ne);
				Cell *tm = mod->addCell(NEW_ID, ID($mux));
				tm->setParam(ID(WIDTH), w);
				tm->setPort(ID::A, SigSpec(State::S0, w));
				tm->setPort(ID::B, dflt);
				tm->setPort(ID::S, ne);
				Wire *tw = mod->addWire(NEW_ID, w);
				tm->setPort(ID::Y, tw);
				Wire *ow = mod->addWire(NEW_ID, w);
				mod->addOr(NEW_ID, acc, tw, ow);
				acc = ow;
				newcells += 4;
			}
			SigSpec root_y = root->getPort(ID::Y);
			for (Cell *m : chain)
				mod->remove(m);
			mod->connect(root_y, acc);
			n++;
			log("  prio-or: %s chain of %d $mux -> OR-merged exclusive terms\n",
			    nm.c_str(), (int)chain.size());
		}
		return n;
	}


	int rewrite_repeated_mux_paths(Module *mod, int &newcells)
	{
		SigMap sigmap(mod);
		struct Node {
			IdString name;
			SigSpec y, a, b, s;
			bool parallel;
		};
		struct Test {
			SigSpec bits;
			bool invert;
		};
		struct Leaf {
			SigSpec data;
			std::vector<Test> path;
		};
		std::map<SigSpec, Node> nodes;
		std::map<SigBit, Cell *> drivers;
		std::set<SigBit> ambiguous, visible;
		for (Wire *w : mod->wires())
			if (w->port_output)
				for (SigBit b : sigmap(SigSpec(w)))
					visible.insert(b);
		for (Cell *c : mod->cells()) {
			for (auto &p : c->connections()) {
				if (!c->output(p.first))
					continue;
				for (SigBit b : sigmap(p.second)) {
					if (b.wire == nullptr)
						continue;
					if (drivers.count(b) && drivers[b] != c)
						ambiguous.insert(b);
					drivers[b] = c;
				}
			}
			if (c->get_bool_attribute(ID::keep) || !c->type.in(ID($mux), ID($pmux)) || !c->hasPort(ID::A) ||
			    !c->hasPort(ID::B) || !c->hasPort(ID::S) || !c->hasPort(ID::Y))
				continue;
			Node n{c->name, sigmap(c->getPort(ID::Y)), sigmap(c->getPort(ID::A)),
			       sigmap(c->getPort(ID::B)), sigmap(c->getPort(ID::S)), c->type == ID($pmux)};
			int w = GetSize(n.y), sw = GetSize(n.s);
			if (w < 2 || GetSize(n.a) != w || sw < 1 ||
			    GetSize(n.b) != w * (n.parallel ? sw : 1) || (!n.parallel && sw != 1))
				continue;
			nodes.emplace(n.y, n);
		}
		for (SigBit b : ambiguous)
			drivers.erase(b);


		auto decode = [&](SigBit sb, SigSpec &ref, Const &code) -> bool {
			if (sb.wire == nullptr || ambiguous.count(sb))
				return false;
			Cell *d = drivers.count(sb) ? drivers[sb] : nullptr;
			if (d == nullptr) {
				ref = SigSpec(sb);
				code = Const(1, 1);
				return true;
			}
			if (!d->hasPort(ID::Y) || sigmap(d->getPort(ID::Y)) != SigSpec(sb))
				return false;
			if (d->type == ID($logic_not) || d->type == ID($not)) {
				ref = sigmap(d->getPort(ID::A));
				if (GetSize(ref) < 1 || ref.is_fully_const() ||
				    (d->type == ID($not) && GetSize(ref) != 1))
					return false;
				code = Const(0, GetSize(ref));
				return true;
			}
			if (!d->type.in(ID($eq), ID($ne)) || !d->hasPort(ID::A) || !d->hasPort(ID::B))
				return false;
			SigSpec a = sigmap(d->getPort(ID::A)), b = sigmap(d->getPort(ID::B));
			if (a.is_fully_const() && !b.is_fully_const())
				std::swap(a, b);
			if (GetSize(a) < 1 || GetSize(a) != GetSize(b) || a.is_fully_const() ||
			    !b.is_fully_const() || !b.is_fully_def())
				return false;
			ref = a;
			code = b.as_const();
			if (d->type == ID($ne)) {
				if (GetSize(ref) != 1 || code != Const(0, 1))
					return false;
				code = Const(1, 1);
			}
			return true;
		};
		std::map<SigSpec, bool> legal;
		for (auto &entry : nodes) {
			const Node &n = entry.second;
			bool ok = true;
			for (SigBit b : n.y)
				if (b.wire == nullptr || ambiguous.count(b))
					ok = false;
			if (n.parallel) {
				SigSpec common;
				std::set<Const> codes;
				for (SigBit sb : n.s) {
					SigSpec ref;
					Const code;
					if (!decode(sb, ref, code) || (!common.empty() && common != ref) || codes.count(code)) {
						ok = false;
						break;
					}
					common = ref;
					codes.insert(code);
				}
			}
			legal[n.y] = ok;
		}
		for (Cell *c : mod->cells())
			for (auto &p : c->connections()) {
				if (!c->input(p.first))
					continue;
				if (c->type.in(ID($mux), ID($pmux)) && p.first.in(ID::A, ID::B))
					continue;
				for (SigBit b : sigmap(p.second))
					visible.insert(b);
			}
		std::vector<Node> roots;
		for (auto &entry : nodes)
			for (SigBit b : entry.first)
				if (visible.count(b)) {
					roots.push_back(entry.second);
					break;
				}
		std::map<std::tuple<int, SigBit, SigBit>, SigBit> controls;
		auto boolean = [&](int op, SigBit a, SigBit b) -> SigBit {
			SigBit zero(State::S0), one(State::S1);
			if (op == 0) {
				if (a == zero) return one;
				if (a == one) return zero;
			} else {
				if (a == b) return a;
				if (op == 1) {
					if (a == zero || b == zero) return zero;
					if (a == one) return b;
					if (b == one) return a;
				} else {
					if (a == one || b == one) return one;
					if (a == zero) return b;
					if (b == zero) return a;
				}
				if (b < a) std::swap(a, b);
			}
			auto key = std::make_tuple(op, a, b);
			if (controls.count(key))
				return controls[key];
			Wire *y = mod->addWire(NEW_ID, 1);
			if (op == 0) mod->addNot(NEW_ID, a, y);
			else if (op == 1) mod->addAnd(NEW_ID, a, b, y);
			else mod->addOr(NEW_ID, a, b, y);
			newcells++;
			controls[key] = SigBit(y);
			return SigBit(y);
		};
		int changed = 0;
		for (const Node &root : roots) {
			std::vector<Leaf> leaves;
			std::set<SigSpec> active;
			int maxdepth = 0;
			auto walk = [&](auto &&self, const SigSpec &data, const std::vector<Test> &path, int depth) -> bool {
				if (depth > 10 || leaves.size() > 100)
					return false;
				maxdepth = std::max(maxdepth, depth);
				auto it = nodes.find(data);
				if (it == nodes.end()) {
					leaves.push_back(Leaf{data, path});
					return leaves.size() <= 100;
				}
				if (!legal[data] || active.count(data))
					return false;
				active.insert(data);
				const Node &n = it->second;
				std::vector<Test> next = path;
				next.push_back(Test{n.s, true});
				if (!self(self, n.a, next, depth + 1))
					return false;
				int arms = n.parallel ? GetSize(n.s) : 1;
				for (int i = 0; i < arms; i++) {
					next = path;
					next.push_back(Test{SigSpec(n.s[n.parallel ? i : 0]), false});
					if (!self(self, n.b.extract(i * GetSize(n.y), GetSize(n.y)), next, depth + 1))
						return false;
				}
				active.erase(data);
				return true;
			};
			if (!walk(walk, root.y, {}, 0) || maxdepth < 3)
				continue;
			std::set<SigSpec> distinct;
			for (const Leaf &leaf : leaves)
				distinct.insert(leaf.data);
			if (leaves.size() < 2 * distinct.size())
				continue;
			std::map<SigSpec, SigBit> grouped;
			for (const Leaf &leaf : leaves) {
				SigBit enable(State::S1);
				for (const Test &test : leaf.path) {
					SigBit term(State::S0);
					for (SigBit b : test.bits)
						term = boolean(2, term, b);
					if (test.invert)
						term = boolean(0, term, SigBit(State::S0));
					enable = boolean(1, enable, term);
				}
				if (grouped.count(leaf.data))
					grouped[leaf.data] = boolean(2, grouped[leaf.data], enable);
				else grouped[leaf.data] = enable;
			}
			std::vector<SigSpec> terms;
			int width = GetSize(root.y);
			for (auto &entry : grouped) {
				if (entry.second == SigBit(State::S0) || entry.first == SigSpec(Const(0, width)))
					continue;
				if (entry.second == SigBit(State::S1)) {
					terms.push_back(entry.first);
					continue;
				}
				Wire *y = mod->addWire(NEW_ID, width);
				mod->addMux(NEW_ID, Const(0, width), entry.first, entry.second, y);
				newcells++;
				terms.push_back(SigSpec(y));
			}
			while (terms.size() > 1) {
				std::vector<SigSpec> next;
				for (size_t i = 0; i < terms.size(); i += 2) {
					if (i + 1 == terms.size()) { next.push_back(terms[i]); continue; }
					Wire *y = mod->addWire(NEW_ID, width);
					mod->addOr(NEW_ID, terms[i], terms[i + 1], y);
					newcells++;
					next.push_back(SigSpec(y));
				}
				terms.swap(next);
			}
			mod->remove(mod->cell(root.name));
			mod->connect(root.y, terms.empty() ? SigSpec(Const(0, width)) : terms[0]);
			changed++;
			log("  repeated-mux-paths: %s, %d paths, %d distinct data values\n",
			    log_id(root.name), int(leaves.size()), int(distinct.size()));
		}
		return changed;
	}

	int rewrite_nested_arithmetic(Module *mod, int &newcells)
	{
		SigMap sigmap(mod);
		struct Node {
			IdString name;
			SigSpec y, a, b, s;
			bool parallel;
		};
		struct Test {
			SigSpec bits;
			bool invert;
		};
		struct Leaf {
			SigSpec data;
			std::vector<Test> path;
		};
		std::map<SigSpec, Node> nodes;
		std::map<SigBit, Cell *> drivers;
		std::set<SigBit> ambiguous, visible;
		for (Wire *w : mod->wires())
			if (w->port_output)
				for (SigBit b : sigmap(SigSpec(w)))
					visible.insert(b);
		for (Cell *c : mod->cells()) {
			for (auto &p : c->connections()) {
				if (!c->output(p.first))
					continue;
				for (SigBit b : sigmap(p.second)) {
					if (b.wire == nullptr)
						continue;
					if (drivers.count(b) && drivers[b] != c)
						ambiguous.insert(b);
					drivers[b] = c;
				}
			}
			if (c->get_bool_attribute(ID::keep) || !c->type.in(ID($mux), ID($pmux)) || !c->hasPort(ID::A) ||
			    !c->hasPort(ID::B) || !c->hasPort(ID::S) || !c->hasPort(ID::Y))
				continue;
			Node n{c->name, sigmap(c->getPort(ID::Y)), sigmap(c->getPort(ID::A)),
			       sigmap(c->getPort(ID::B)), sigmap(c->getPort(ID::S)), c->type == ID($pmux)};
			int w = GetSize(n.y), sw = GetSize(n.s);
			if (w < 2 || GetSize(n.a) != w || sw < 1 ||
			    GetSize(n.b) != w * (n.parallel ? sw : 1) || (!n.parallel && sw != 1))
				continue;
			nodes.emplace(n.y, n);
		}
		for (SigBit b : ambiguous)
			drivers.erase(b);


		auto decode = [&](SigBit sb, SigSpec &ref, Const &code) -> bool {
			if (sb.wire == nullptr || ambiguous.count(sb))
				return false;
			Cell *d = drivers.count(sb) ? drivers[sb] : nullptr;
			if (d == nullptr) {
				ref = SigSpec(sb);
				code = Const(1, 1);
				return true;
			}
			if (!d->hasPort(ID::Y) || sigmap(d->getPort(ID::Y)) != SigSpec(sb))
				return false;
			if (d->type == ID($logic_not) || d->type == ID($not)) {
				ref = sigmap(d->getPort(ID::A));
				if (GetSize(ref) < 1 || ref.is_fully_const() ||
				    (d->type == ID($not) && GetSize(ref) != 1))
					return false;
				code = Const(0, GetSize(ref));
				return true;
			}
			if (!d->type.in(ID($eq), ID($ne)) || !d->hasPort(ID::A) || !d->hasPort(ID::B))
				return false;
			SigSpec a = sigmap(d->getPort(ID::A)), b = sigmap(d->getPort(ID::B));
			if (a.is_fully_const() && !b.is_fully_const())
				std::swap(a, b);
			if (GetSize(a) < 1 || GetSize(a) != GetSize(b) || a.is_fully_const() ||
			    !b.is_fully_const() || !b.is_fully_def())
				return false;
			ref = a;
			code = b.as_const();
			if (d->type == ID($ne)) {
				if (GetSize(ref) != 1 || code != Const(0, 1))
					return false;
				code = Const(1, 1);
			}
			return true;
		};
		std::map<SigSpec, bool> legal;
		for (auto &entry : nodes) {
			const Node &n = entry.second;
			bool ok = true;
			for (SigBit b : n.y)
				if (b.wire == nullptr || ambiguous.count(b))
					ok = false;
			if (n.parallel) {
				SigSpec common;
				std::set<Const> codes;
				for (SigBit sb : n.s) {
					SigSpec ref;
					Const code;
					if (!decode(sb, ref, code) || (!common.empty() && common != ref) || codes.count(code)) {
						ok = false;
						break;
					}
					common = ref;
					codes.insert(code);
				}
			}
			legal[n.y] = ok;
		}
		for (Cell *c : mod->cells())
			for (auto &p : c->connections()) {
				if (!c->input(p.first))
					continue;
				if (c->type.in(ID($mux), ID($pmux)) && p.first.in(ID::A, ID::B))
					continue;
				for (SigBit b : sigmap(p.second))
					visible.insert(b);
			}
		std::vector<Node> roots;
		for (auto &entry : nodes)
			for (SigBit b : entry.first)
				if (visible.count(b)) {
					roots.push_back(entry.second);
					break;
				}
		std::map<std::tuple<int, SigBit, SigBit>, SigBit> controls;
		auto boolean = [&](int op, SigBit a, SigBit b) -> SigBit {
			SigBit zero(State::S0), one(State::S1);
			if (op == 0) {
				if (a == zero) return one;
				if (a == one) return zero;
			} else {
				if (a == b) return a;
				if (op == 1) {
					if (a == zero || b == zero) return zero;
					if (a == one) return b;
					if (b == one) return a;
				} else {
					if (a == one || b == one) return one;
					if (a == zero) return b;
					if (b == zero) return a;
				}
				if (b < a) std::swap(a, b);
			}
			auto key = std::make_tuple(op, a, b);
			if (controls.count(key))
				return controls[key];
			Wire *y = mod->addWire(NEW_ID, 1);
			if (op == 0) mod->addNot(NEW_ID, a, y);
			else if (op == 1) mod->addAnd(NEW_ID, a, b, y);
			else mod->addOr(NEW_ID, a, b, y);
			newcells++;
			controls[key] = SigBit(y);
			return SigBit(y);
		};
		std::sort(roots.begin(),roots.end(),[](const Node &a,const Node &b) {return a.name.str()<b.name.str();});
		int changed = 0;
		for (const Node &root : roots) {
			std::vector<Leaf> leaves;
			std::set<SigSpec> active;
			int maxdepth = 0;
			std::set<Cell *> visited;
			auto walk = [&](auto &&self, const SigSpec &data, const std::vector<Test> &path, int depth) -> bool {
				if (depth > 10 || leaves.size() > 100)
					return false;
				maxdepth = std::max(maxdepth, depth);
				auto it = nodes.find(data);
				if (it == nodes.end()) {
					leaves.push_back(Leaf{data, path});
					return leaves.size() <= 100;
				}
				if (!legal[data] || active.count(data))
					return false;
				active.insert(data);
				const Node &n = it->second;
				visited.insert(mod->cell(n.name));
				std::vector<Test> next = path;
				next.push_back(Test{n.s, true});
				if (!self(self, n.a, next, depth + 1))
					return false;
				int arms = n.parallel ? GetSize(n.s) : 1;
				for (int i = 0; i < arms; i++) {
					next = path;
					next.push_back(Test{SigSpec(n.s[n.parallel ? i : 0]), false});
					if (!self(self, n.b.extract(i * GetSize(n.y), GetSize(n.y)), next, depth + 1))
						return false;
				}
				active.erase(data);
				return true;
			};
			if (!walk(walk, root.y, {}, 0) || maxdepth < 2)
				continue;

            const int width = GetSize(root.y);
            if (width < 6) continue;
            // An internal select output must not escape this selected tree.
            bool tree_private = true;
            for (Cell *c : mod->cells())
                for (auto &p : c->connections()) {
                    if (!c->input(p.first) || visited.count(c)) continue;
                    for (SigBit bit : sigmap(p.second)) {
                        auto di = drivers.find(bit);
                        if (di != drivers.end() && visited.count(di->second) && di->second->name != root.name)
                            tree_private = false;
                    }
                }
            for (Wire *w : mod->wires()) if (w->port_output)
                for (SigBit bit : sigmap(SigSpec(w))) {
                    auto di=drivers.find(bit);
                    if(di!=drivers.end() && visited.count(di->second) && di->second->name!=root.name) tree_private=false;
                }
            if (!tree_private) continue;
            struct Operation { Cell *cell; SigSpec other, common; bool sub; std::vector<int> leaves; };
            auto signal_key = [](const SigSpec &signal) {
                std::string key;
                for(SigBit bit:signal) {
                    if(bit.wire) key += "w"+std::to_string(bit.wire->name.str().size())+":"+bit.wire->name.str()+":"+std::to_string(bit.offset)+";";
                    else key += "c"+std::to_string(int(bit.data))+";";
                }
                return key;
            };
            std::map<std::string, std::map<std::string, Operation>> groups;
            std::map<std::string, Operation> all_ops;
            std::set<SigBit> output_bits;
            for (Wire *w : mod->wires()) if (w->port_output)
                for (SigBit bit : sigmap(SigSpec(w))) output_bits.insert(bit);
            for (int k=0; k<int(leaves.size()); k++) {
                const SigSpec &data = leaves[k].data;
                if (GetSize(data) != width || data[0].wire == nullptr || !drivers.count(data[0])) continue;
                Cell *op = drivers.at(data[0]);
                if (!op->type.in(ID($add), ID($sub)) || op->get_bool_attribute(ID::keep) ||
                    !op->hasPort(ID::A) || !op->hasPort(ID::B) || !op->hasPort(ID::Y) ||
                    sigmap(op->getPort(ID::Y)) != data ||
                    GetSize(op->getPort(ID::A)) != width || GetSize(op->getPort(ID::B)) != width ||
                    op->getParam(ID::Y_WIDTH).as_int() != width ||
                    op->getParam(ID::A_WIDTH).as_int() != width || op->getParam(ID::B_WIDTH).as_int() != width) continue;
                bool private_op = true;
                for (SigBit bit : data) if (ambiguous.count(bit) || output_bits.count(bit)) private_op = false;
                for (Cell *c : mod->cells()) {
                    if (visited.count(c)) continue;
                    for (auto &p : c->connections()) if (c->input(p.first))
                        for (SigBit bit : sigmap(p.second))
                            if (std::find(data.begin(),data.end(),bit) != data.end()) private_op = false;
                }
                if (!private_op) continue;
                SigSpec aa=sigmap(op->getPort(ID::A)), bb=sigmap(op->getPort(ID::B));
                auto record = [&](const SigSpec &common, const SigSpec &other) {
                    if (common.is_fully_const()) return;
                    auto &entry=groups[signal_key(common)][op->name.str()];
                    entry.cell=op;entry.other=other;entry.common=common;entry.sub=op->type==ID($sub);entry.leaves.push_back(k);
                };
                auto &any=all_ops[op->name.str()];any.cell=op;any.other=aa;any.common=bb;any.sub=op->type==ID($sub);any.leaves.push_back(k);
                record(bb,aa);
                if (op->type==ID($add) && aa!=bb) record(aa,bb);
            }
            auto best=groups.end();
            for (auto it=groups.begin();it!=groups.end();++it)
                if (it->second.size() >= 3 && (best==groups.end() || it->second.size()>best->second.size())) best=it;
            if (best==groups.end()) continue;
            if (best->second.size()*2 >= all_ops.size()) {
                for(auto &entry:all_ops) if(!best->second.count(entry.first)) best->second[entry.first]=entry.second;
            }
            std::set<SigBit> forbidden;
            for (Cell *c:visited) for(SigBit bit:sigmap(c->getPort(ID::Y))) forbidden.insert(bit);
            for (auto &entry:best->second) for(SigBit bit:sigmap(entry.second.cell->getPort(ID::Y))) forbidden.insert(bit);
            std::set<SigBit> active_inputs, safe_inputs;
            auto safe = [&](auto &&self,SigBit bit)->bool {
                if(bit.wire==nullptr) return true;
                if(ambiguous.count(bit)||forbidden.count(bit)) return false;
                if(safe_inputs.count(bit)) return true;
                if(!active_inputs.insert(bit).second) return false;
                if(drivers.count(bit)) {
                    Cell *d=drivers.at(bit);
                    bool stateful=d->type.in(ID($dff),ID($dffe),ID($adff),ID($adffe),ID($sdff),ID($sdffe),ID($sdffce),ID($dlatch),ID($adlatch));
                    if(!stateful) {
                        if(d->type.str().empty()||d->type.str()[0]!='$') return false;
                        for(auto &p:d->connections()) if(d->input(p.first))
                            for(SigBit input:sigmap(p.second)) if(!self(self,input)) return false;
                    }
                }
                active_inputs.erase(bit);safe_inputs.insert(bit);return true;
            };
            bool inputs_safe=true;
            for(auto &entry:best->second) for(IdString port:{ID::A,ID::B})
                for(SigBit bit:sigmap(entry.second.cell->getPort(port))) if(!safe(safe,bit)) inputs_safe=false;
            for(const Leaf &leaf:leaves) for(const Test &test:leaf.path)
                for(SigBit bit:test.bits) if(!safe(safe,bit)) inputs_safe=false;
            // A result can be shared only at complete selected data leaves.
            // Other leaves may contain slices or expressions using that result.
            for(const Leaf &leaf:leaves) {
                bool selected_result=false;
                for(auto &entry:best->second)
                    if(leaf.data==sigmap(entry.second.cell->getPort(ID::Y))) selected_result=true;
                if(!selected_result)
                    for(SigBit bit:leaf.data) if(!safe(safe,bit)) inputs_safe=false;
            }
            if(!inputs_safe) continue;
            SigSpec alternatives, right_alternatives, enables;
            SigBit subtract(State::S0);
            for(auto &entry:best->second) {
                SigBit enabled(State::S0);
                for(int index:entry.second.leaves) {
                    SigBit enable(State::S1);
                    for(const Test &test:leaves[index].path) {
                        SigBit term(State::S0);
                        for(SigBit bit:test.bits) term=boolean(2,term,bit);
                        if(test.invert) term=boolean(0,term,SigBit(State::S0));
                        enable=boolean(1,enable,term);
                    }
                    enabled=boolean(2,enabled,enable);
                }
                alternatives.append(entry.second.other);right_alternatives.append(entry.second.common);enables.append(enabled);
                if(entry.second.sub) subtract=boolean(2,subtract,enabled);
            }
            Wire *operand=mod->addWire(NEW_ID,width), *result=mod->addWire(NEW_ID,width);
            mod->addPmux(NEW_ID,Const(0,width),alternatives,enables,operand);
            Wire *right=mod->addWire(NEW_ID,width);
            mod->addPmux(NEW_ID,Const(0,width),right_alternatives,enables,right);
            Cell *shared=mod->addCell(NEW_ID,ID($alu));
            shared->setParam(ID::A_WIDTH,width);shared->setParam(ID::B_WIDTH,width);shared->setParam(ID::Y_WIDTH,width);
            shared->setParam(ID::A_SIGNED,false);shared->setParam(ID::B_SIGNED,false);
            shared->setPort(ID::A,operand);shared->setPort(ID::B,right);
            shared->setPort(ID::CI,subtract);shared->setPort(ID::BI,subtract);shared->setPort(ID::Y,result);
            shared->setPort(ID::X,mod->addWire(NEW_ID,width));shared->setPort(ID::CO,mod->addWire(NEW_ID,width));
            int merged=0;
            for(auto &entry:best->second) {
                mod->connect(entry.second.cell->getPort(ID::Y),result);
                mod->remove(entry.second.cell);merged++;
            }
            newcells+=2;changed++;
            log("  nested-arithmetic: %s merges %d mutually exclusive add/sub operations.\n",log_id(root.name),merged);
            return changed;

		}
		return changed;
	}

	int rewrite_priority_cells(Module *mod, int &newcells)
	{
		int n = 0;
		std::map<SigBit, Cell *> drv;
		for (Cell *d : mod->cells())
			if (d->hasPort(ID::Y))
				for (SigBit b : d->getPort(ID::Y))
					if (b.wire != nullptr)
						drv[b] = d;


		std::vector<Cell *> prios;
		for (Cell *c : mod->cells()) {
			if (c->type != ID($pmux))
				continue;
			SigSpec S = c->getPort(ID::S);
			SigSpec Bp = c->getPort(ID::B);
			SigSpec Y = c->getPort(ID::Y);
			int w = GetSize(Y), sw = GetSize(S);
			if (w <= 0 || sw < 2 || GetSize(Bp) != w * sw || !c->hasPort(ID::A))
				continue;
			SigSpec A = c->getPort(ID::A);
			if (GetSize(A) != w)
				continue;


			bool prio = true;
			for (int i = 0; i < sw && prio; i++) {
				SigBit sb = S[i];
				Cell *e = (sb.wire != nullptr && drv.count(sb)) ? drv[sb] : nullptr;
				if (sb.wire == nullptr || (e != nullptr && e->type == ID($eq)))
					prio = false;
			}
			if (!prio)
				continue;
			prios.push_back(c);
		}
		for (Cell *c : prios) {
			SigSpec S = c->getPort(ID::S);
			SigSpec Bp = c->getPort(ID::B);
			SigSpec Y = c->getPort(ID::Y);
			SigSpec A = c->getPort(ID::A);
			int w = GetSize(Y), sw = GetSize(S);

			SigSpec any = S[0];
			Wire *cur = mod->addWire(NEW_ID, w);
			mod->addMux(NEW_ID, A, Bp.extract(0, w), any, cur);
			newcells++;
			for (int i = 1; i < sw; i++) {
				Wire *nany = mod->addWire(NEW_ID, 1);
				mod->addNot(NEW_ID, any, nany);
				Wire *oi = mod->addWire(NEW_ID, 1);
				mod->addAnd(NEW_ID, S[i], nany, oi);
				Wire *yi = mod->addWire(NEW_ID, w);
				mod->addMux(NEW_ID, cur, Bp.extract(i * w, w), oi, yi);
				cur = yi;
				newcells += 3;
			}
			mod->remove(c);
			mod->connect(Y, cur);
			n++;
		}
		return n;
	}


	int rewrite_decode_share(Module *mod, int &newcells, int min_width = 3)
	{


		for (Cell *c : mod->cells())
			if (c->type.in(ID($mem_v2), ID($memrd_v2), ID($memwr_v2), ID($meminit),
			               ID($mem), ID($memrd), ID($memwr), ID($meminit)))
				return 0;

		std::vector<Cell *> eqs;
		for (Cell *c : mod->cells()) {
			if (c->type != ID($eq))
				continue;
			if (!c->hasPort(ID::A) || !c->hasPort(ID::B) || !c->hasPort(ID::Y))
				continue;
			SigSpec a = c->getPort(ID::A), b = c->getPort(ID::B);
			if (GetSize(a) < min_width || GetSize(b) != GetSize(a) || GetSize(c->getPort(ID::Y)) != 1)
				continue;
			bool ok = true;
			for (SigBit bit : a)
				if (bit.wire == nullptr) { ok = false; break; }
			for (SigBit bit : b)
				if (bit.wire != nullptr ||
				    (bit.data != State::S0 && bit.data != State::S1)) { ok = false; break; }
			if (!ok)
				continue;
			eqs.push_back(c);
		}
		int n = 0;
		std::set<Cell *> used;


		const int kMaxPairs = 4;
		for (size_t i = 0; i < eqs.size() && n < kMaxPairs; i++) {
			if (used.count(eqs[i]))
				continue;
			for (size_t j = i + 1; j < eqs.size(); j++) {
				if (used.count(eqs[j]))
					continue;
				Cell *e1 = eqs[i], *e2 = eqs[j];
				SigSpec a1 = e1->getPort(ID::A), a2 = e2->getPort(ID::A);
				Const k1 = e1->getPort(ID::B).as_const();
				Const k2 = e2->getPort(ID::B).as_const();

				bool same_ref = GetSize(a1) == GetSize(a2);
				for (int k = 0; same_ref && k < GetSize(a1); k++)
					if (a1[k].wire != a2[k].wire || a1[k].offset != a2[k].offset)
						same_ref = false;
				if (!same_ref)
					continue;

				int diff = -1;
				for (int k = 0; k < GetSize(k1); k++) {
					if (k1[k] == k2[k])
						continue;
					if (diff >= 0) { diff = -2; break; }
					diff = k;
				}
				if (diff < 0)
					continue;

				SigBit y1 = e1->getPort(ID::Y)[0];
				SigBit y2 = e2->getPort(ID::Y)[0];
				if (y1.wire == nullptr || y2.wire == nullptr || y1 == y2)
					continue;

				SigSpec agree;
				for (int k = 0; k < GetSize(k1); k++) {
					if (k1[k] != k2[k]) continue;
					SigBit value = a1[k];
					if (k1[k] == State::S0) {
						Wire *inverted = mod->addWire(NEW_ID, 1);
						mod->addNot(NEW_ID, value, inverted);
						value = SigBit(inverted);
						newcells++;
					}
					agree.append(value);
				}
				SigBit shared;
				if (GetSize(agree) == 1) {
					shared = agree[0];
				} else {
					Wire *sh = mod->addWire(NEW_ID, 1);
					mod->addReduceAnd(NEW_ID, agree, SigSpec(sh));
					shared = SigBit(sh);
					newcells++;
				}


				SigBit term[2];
				Const kk[2] = {k1, k2};
				SigBit ys[2] = {y1, y2};
				for (int t = 0; t < 2; t++) {
					SigBit refp = a1[diff];
					if (kk[t][diff] != State::S1) {
						Wire *nb = mod->addWire(NEW_ID, 1);
						mod->addNot(NEW_ID, refp, SigSpec(nb));
						refp = SigBit(nb);
						newcells++;
					}
					mod->addAnd(NEW_ID, shared, refp, SigSpec(ys[t]));
					term[t] = ys[t];
					newcells++;
				}

				mod->remove(e1);
				mod->remove(e2);
				used.insert(e1);
				used.insert(e2);
				n++;
				break;
			}
		}
	if (n)
		log("  stage F: factored %d $eq pair(s) through shared decode prefixes\n", n);
	return n;
}


	pool<SigBit> explicit_init_aliases(Module *mod, SigMap &sigmap)
	{
		pool<SigBit> initialized;
		for (Wire *wire : mod->wires())
			if (wire->attributes.count(ID(init)))
				for (SigBit bit : sigmap(SigSpec(wire)))
					initialized.insert(bit);
		return initialized;
	}

	bool uninitialized_positive_ff(Cell *cell, SigMap &sigmap,
	                               const pool<SigBit> &initialized)
	{
		if (!cell->type.in(ID($adff), ID($dff)) ||
		    !cell->parameters.count(ID(WIDTH)) ||
		    !cell->parameters.count(ID(CLK_POLARITY)) ||
		    cell->parameters.at(ID(CLK_POLARITY)).as_int() != 1 ||
		    !cell->hasPort(ID(D)) || !cell->hasPort(ID(Q)) || !cell->hasPort(ID(CLK)))
			return false;
		int width = cell->parameters.at(ID(WIDTH)).as_int();
		SigSpec d = cell->getPort(ID(D)), q = cell->getPort(ID(Q));
		SigSpec clk = cell->getPort(ID(CLK));
		if (width < 1 || GetSize(d) != width || GetSize(q) != width ||
		    GetSize(clk) != 1 || clk[0].wire == nullptr)
			return false;
		for (SigBit bit : q)
			if (bit.wire == nullptr || sigmap(bit).wire == nullptr ||
			    initialized.count(sigmap(bit)))
				return false;
		return true;
	}

	bool positive_ff(Cell *cell, SigMap &sigmap)
	{
		pool<SigBit> empty;
		return uninitialized_positive_ff(cell, sigmap, empty);
	}

	int rewrite_hold_extract(Module *mod, int &newcells)
	{


		for (Cell *c : mod->cells())
			if (c->type.in(ID($mem_v2), ID($memrd_v2), ID($memwr_v2), ID($meminit),
			               ID($mem), ID($memrd), ID($memwr), ID($meminit)))
				return 0;

		SigMap init_sigmap(mod);
		auto initialized = explicit_init_aliases(mod, init_sigmap);

		std::map<SigBit, Cell *> drv;
		for (Cell *c : mod->cells())
			if (c->hasPort(ID::Y))
				for (SigBit b : c->getPort(ID::Y))
					if (b.wire != nullptr)
						drv[b] = c;


		struct HPath {
			SigBit data;
			bool is_hold;
			bool is_default;
			std::vector<std::pair<SigBit, bool>> muxl;
			std::vector<SigBit> pmuxl;
			int arm;
		};


		std::map<std::string, SigBit> and_cache, or_cache, not_cache;
		auto lit_key = [](const std::vector<std::pair<SigBit, bool>> &lits) {
			std::vector<std::string> parts;
			for (auto &l : lits)
				parts.push_back(l.first.wire->name.str() + ":" +
				                std::to_string(l.first.offset) +
				                (l.second ? "+" : "-"));
			std::sort(parts.begin(), parts.end());
			std::string k;
			for (auto &p : parts) k += p + "|";
			return k;
		};
		auto sig_key = [](const std::vector<SigBit> &sigs) {
			std::vector<std::string> parts;
			for (auto &s : sigs)
				parts.push_back(s.wire->name.str() + ":" + std::to_string(s.offset));
			std::sort(parts.begin(), parts.end());
			std::string k;
			for (auto &p : parts) k += p + "|";
			return k;
		};
		auto get_and_lits = [&](const std::vector<std::pair<SigBit, bool>> &lits) -> SigBit {
			if (lits.empty())
				return SigBit(State::S1);
			std::string k = lit_key(lits);
			auto it = and_cache.find(k);
			if (it != and_cache.end())
				return it->second;
			SigBit acc;
			for (auto &l : lits) {
				SigBit v = l.first;
				if (!l.second) {
					Wire *w = mod->addWire(NEW_ID, 1);
					mod->addNot(NEW_ID, v, SigSpec(w));
					v = SigBit(w);
					newcells++;
				}
				if (acc.wire == nullptr) {
					acc = v;
				} else {
					Wire *w = mod->addWire(NEW_ID, 1);
					mod->addAnd(NEW_ID, acc, v, SigSpec(w));
					acc = SigBit(w);
					newcells++;
				}
			}
			and_cache[k] = acc;
			return acc;
		};
		auto get_or = [&](const std::vector<SigBit> &sigs) -> SigBit {
			if (sigs.empty())
				return SigBit(State::S0);
			if (sigs.size() == 1)
				return sigs[0];
			std::string k = sig_key(sigs);
			auto it = or_cache.find(k);
			if (it != or_cache.end())
				return it->second;
			std::vector<SigBit> v(sigs.begin(), sigs.end());
			Wire *acc = mod->addWire(NEW_ID, 1);
			mod->addOr(NEW_ID, v[0], v[1], SigSpec(acc));
			newcells++;
			for (size_t i = 2; i < v.size(); i++) {
				Wire *nx = mod->addWire(NEW_ID, 1);
				mod->addOr(NEW_ID, SigBit(acc), v[i], SigSpec(nx));
				acc = nx;
				newcells++;
			}
			or_cache[k] = SigBit(acc);
			return SigBit(acc);
		};
		auto get_not = [&](SigBit s) -> SigBit {
			if (s.wire == nullptr)
				return SigBit(s.data == State::S1 ? State::S0 : State::S1);
			std::string k = s.wire->name.str() + ":" + std::to_string(s.offset);
			auto it = not_cache.find(k);
			if (it != not_cache.end())
				return it->second;
			Wire *w = mod->addWire(NEW_ID, 1);
			mod->addNot(NEW_ID, s, SigSpec(w));
			newcells++;
			not_cache[k] = SigBit(w);
			return SigBit(w);
		};
		auto sig_bit_key = [](SigBit s) -> std::string {
			if (s.wire == nullptr)
				return std::string("const:") + (s.data == State::S1 ? "1" : "0");
			return s.wire->name.str() + ":" + std::to_string(s.offset);
		};


		std::map<std::string, SigBit> and2_cache;
		auto get_and2 = [&](SigBit a, SigBit b) -> SigBit {
			if (a == b)
				return a;
			std::string ka = sig_bit_key(a), kb = sig_bit_key(b);
			if (ka > kb) { std::swap(ka, kb); std::swap(a, b); }
			std::string k = ka + "&" + kb;
			auto it = and2_cache.find(k);
			if (it != and2_cache.end())
				return it->second;
			Wire *w = mod->addWire(NEW_ID, 1);
			mod->addAnd(NEW_ID, a, b, SigSpec(w));
			newcells++;
			and2_cache[k] = SigBit(w);
			return SigBit(w);
		};


		auto leafy = [&](SigBit d, SigBit qbit) -> bool {
			if (d == qbit || d.wire == nullptr)
				return d.wire == nullptr ? (d.data == State::S0 || d.data == State::S1)
			                          : true;
			auto it = drv.find(d);
			if (it == drv.end())
				return true;
			return !it->second->type.in(ID($mux), ID($pmux));
		};


		auto h_walk = [&](auto &&self, SigBit cur, SigBit qbit,
		                  std::vector<std::pair<SigBit, bool>> &muxl,
		                  std::vector<SigBit> &pmuxl, int arm, bool under_def,
		                  std::vector<HPath> &out, int depth) -> bool {
			if (depth > 24 || out.size() > 64)
				return false;
			if (cur == qbit) {
				out.push_back({cur, true, under_def, muxl, pmuxl, arm});
				return true;
			}
			if (cur.wire == nullptr) {
				if (cur.data != State::S0 && cur.data != State::S1)
					return false;
				out.push_back({cur, false, under_def, muxl, pmuxl, arm});
				return true;
			}
			auto it = drv.find(cur);
			if (it == drv.end()) {
				out.push_back({cur, false, under_def, muxl, pmuxl, arm});
				return true;
			}
			Cell *c = it->second;
			if (c->type == ID($mux)) {
				SigSpec A = c->getPort(ID::A), B = c->getPort(ID::B), S = c->getPort(ID::S);
				SigSpec Y = c->getPort(ID::Y);
				if (GetSize(S) != 1 || S[0].wire == nullptr)
					return false;
				int off = -1;
				for (int k = 0; k < GetSize(Y); k++)
					if (Y[k] == cur) { off = k; break; }
				if (off < 0 || off >= GetSize(A) || off >= GetSize(B))
					return false;
				if (pmuxl.size() > 0)
					return false;
				muxl.push_back({S[0], true});
				if (!self(self, B[off], qbit, muxl, pmuxl, INT_MAX, under_def, out, depth + 1)) {
					muxl.pop_back();
					return false;
				}
				muxl.pop_back();
				muxl.push_back({S[0], false});
				if (!self(self, A[off], qbit, muxl, pmuxl, INT_MAX, under_def, out, depth + 1)) {
					muxl.pop_back();
					return false;
				}
				muxl.pop_back();
				return true;
			}
			if (c->type == ID($pmux)) {
				SigSpec A = c->getPort(ID::A), B = c->getPort(ID::B), S = c->getPort(ID::S);
				SigSpec Y = c->getPort(ID::Y);
				int width = GetSize(A);
				if (width == 0 || GetSize(Y) != width || GetSize(S) == 0 ||
				    GetSize(B) != GetSize(S) * width)
					return false;
				if (pmuxl.size() > 0)
					return false;
				int off = -1;
				for (int k = 0; k < GetSize(Y); k++)
					if (Y[k] == cur) { off = k; break; }
				if (off < 0)
					return false;
				for (int k = 0; k < GetSize(S); k++) {
					if (!leafy(B[k * width + off], qbit))
						return false;
					pmuxl.push_back(S[k]);
					bool ok = self(self, B[k * width + off], qbit, muxl, pmuxl, k,
					               false, out, depth + 1);
					pmuxl.pop_back();
					if (!ok)
						return false;
				}
				return self(self, A[off], qbit, muxl, pmuxl, INT_MAX, true, out, depth + 1);
			}

			out.push_back({cur, false, under_def, muxl, pmuxl, arm});
			return true;
		};


		auto h_disjoint = [&](const std::vector<SigBit> &sels) -> bool {
			std::vector<std::pair<SigSpec, Const>> dec;
			for (SigBit s : sels) {
				auto it = drv.find(s);
				if (it == drv.end() || it->second->type != ID($eq))
					return false;
				Cell *e = it->second;
				SigSpec a = e->getPort(ID::A), b = e->getPort(ID::B);
				if (GetSize(a) < 1 || GetSize(b) != GetSize(a) ||
				    GetSize(e->getPort(ID::Y)) != 1)
					return false;
				bool ok = true;
				for (SigBit bit : a)
					if (bit.wire == nullptr) { ok = false; break; }
				for (SigBit bit : b)
					if (bit.wire != nullptr ||
					    (bit.data != State::S0 && bit.data != State::S1)) { ok = false; break; }
				if (!ok)
					return false;
				dec.push_back({a, b.as_const()});
			}
			for (size_t i = 0; i < dec.size(); i++)
				for (size_t j = i + 1; j < dec.size(); j++) {
					if (dec[i].first != dec[j].first)
						return false;
					if (dec[i].second == dec[j].second)
						return false;
				}
			return true;
		};


		std::vector<Cell *> ffs;
		for (Cell *c : mod->cells())
			if (c->type == ID($dff))
				ffs.push_back(c);

		int n = 0;


		std::map<std::tuple<SigBit, SigBit, SigBit>, SigBit> mux_cache;
		for (Cell *c : ffs) {
			int w = c->parameters[ID(WIDTH)].as_int();
			if (w < 1 || c->parameters[ID(CLK_POLARITY)].as_int() != 1)
				continue;
			SigSpec D = c->getPort(ID(D)), Q = c->getPort(ID(Q));
			if (GetSize(D) != w || GetSize(Q) != w)
				continue;
			if (!uninitialized_positive_ff(c, init_sigmap, initialized))
				continue;
			SigBit clk = c->getPort(ID(CLK))[0];
			if (clk.wire == nullptr)
				continue;

			struct BitPlan {
				SigBit q;
				SigBit d;
				SigBit ena;
			};
			std::vector<BitPlan> plan;
			bool all_ok = true;


			for (int i = 0; i < w && all_ok; i++) {
				std::vector<HPath> paths;
				std::vector<std::pair<SigBit, bool>> muxl;
				std::vector<SigBit> pmuxl;
				if (!h_walk(h_walk, D[i], Q[i], muxl, pmuxl, INT_MAX, false, paths, 0)) {
					all_ok = false;
					break;
				}

				const HPath *def = nullptr;
				std::vector<const HPath *> writes, arm_holds;
				std::vector<SigBit> all_sels;
				for (auto &p : paths) {
					for (SigBit s : p.pmuxl)
						all_sels.push_back(s);
					if (p.pmuxl.size() > 1) { all_ok = false; break; }
					if (p.pmuxl.empty() && !p.is_default && !p.is_hold) {
						all_ok = false;
						break;
					}
					if (p.is_default)
						def = &p;
					else if (!p.is_hold && p.pmuxl.size() == 1)
						writes.push_back(&p);
					else if (p.is_hold && p.pmuxl.size() == 1)
						arm_holds.push_back(&p);

				}
				if (!all_ok)
					break;
				if (!h_disjoint(all_sels)) { all_ok = false; break; }

				std::vector<std::pair<SigBit, bool>> outer;
				bool outer_init = false;
				for (auto *p : writes) {
					if (!outer_init) {
						outer = p->muxl;
						outer_init = true;
					} else {
						std::vector<std::pair<SigBit, bool>> nx;
						for (auto &l : outer)
							for (auto &m : p->muxl)
								if (l.first == m.first && l.second == m.second) {
									nx.push_back(l);
									break;
								}
						outer = nx;
					}
				}


				bool default_writes = (def != nullptr && !def->is_hold);
				if (!default_writes && writes.empty())
					{ all_ok = false; break; }
				SigBit ena_case;
				if (default_writes) {
					std::vector<SigBit> hs;
					for (auto *p : arm_holds)
						hs.push_back(p->pmuxl[0]);
					ena_case = get_or(hs);
					ena_case = get_not(ena_case);
				} else {
					std::vector<SigBit> ws;
					for (auto *p : writes)
						ws.push_back(p->pmuxl[0]);
					ena_case = get_or(ws);
				}
				SigBit ena = ena_case;
				if (!outer.empty())
					ena = get_and2(get_and_lits(outer), ena_case);


				std::vector<const HPath *> wr = writes;
				std::sort(wr.begin(), wr.end(),
				          [](const HPath *a, const HPath *b) { return a->arm < b->arm; });
				SigBit dacc;
				if (default_writes)
					dacc = def->data;
				else
					dacc = wr.empty() ? SigBit(State::S0) : wr.back()->data;
				for (auto rit = wr.rbegin(); rit != wr.rend(); ++rit) {
					SigBit sel = (*rit)->pmuxl[0];
					SigBit data = (*rit)->data;
					auto key = std::make_tuple(dacc, data, sel);
					auto cached = mux_cache.find(key);
					if (cached != mux_cache.end()) {
						dacc = cached->second;
						continue;
					}
					Wire *mw = mod->addWire(NEW_ID, 1);
					Cell *mc = mod->addMux(NEW_ID, dacc, data, sel, SigSpec(mw));
					mc->setParam(ID(WIDTH), 1);
					dacc = SigBit(mw);
					mux_cache.emplace(key, dacc);
					newcells++;
				}
				plan.push_back({Q[i], dacc, ena});
			}
			if (!all_ok || plan.empty() || GetSize(plan) != w)
				continue;

			std::map<SigBit, std::vector<int>> groups;
			for (int i = 0; i < w; i++)
				groups[plan[i].ena].push_back(i);
			for (auto &g : groups) {
				SigSpec dd, qq;
				for (int idx : g.second) {


					dd.append(plan[idx].d);
					qq.append(plan[idx].q);
				}
				Cell *rc = mod->addCell(NEW_ID, ID($dffe));
				rc->setParam(ID(WIDTH), GetSize(dd));
				rc->setParam(ID(CLK_POLARITY), 1);
				rc->setParam(ID(EN_POLARITY), 1);
				rc->setPort(ID::CLK, clk);
				rc->setPort(ID::EN, g.first);
				rc->setPort(ID::D, dd);
				rc->setPort(ID::Q, qq);
				newcells++;
			}
			mod->remove(c);
			n += w;
		}
		if (n)
			log("  stage H: extracted %d FF bit(s) into shared-enable $dffe groups\n", n);
		return n;
	}


	int rewrite_sclr_promo(RTLIL::Design *design, Module *mod, int &newcells)
	{
		SigMap init_sigmap(mod);
		FfInitVals initvals(&init_sigmap, mod);
		bool eligible_ff = false;
		for (Cell *cell : mod->cells())
			if (positive_ff(cell, init_sigmap)) {
				eligible_ff = true;
				break;
			}
		if (!eligible_ff)
			return 0;

		bool has_mem = false;
		for (Cell *c : mod->cells())
			if (c->type.in(ID($mem_v2), ID($memrd_v2), ID($memwr_v2), ID($meminit),
			               ID($mem), ID($memrd), ID($memwr), ID($meminit)))
				{ has_mem = true; break; }
		if (sclr_promo_rom_only && !has_mem) {


			log("  stage G: -sclr-promo-rom-only and the module carries no "
			    "constant-ROM context; left untouched\n");
			return 0;
		}
		if (has_mem) {
			Pass::call_on_module(design, mod, "memory_collect");
			bool dissolvable = true;
			for (Mem &m : Mem::get_all_memories(mod)) {
				if (!m.wr_ports.empty()) { dissolvable = false; break; }
				for (auto &rd : m.rd_ports)
					if (rd.clk_enable) { dissolvable = false; break; }
				if (!dissolvable)
					break;
			}
			if (!dissolvable) {
				log("  stage G: module carries a memory that is not a write-free "
				    "async-read ROM (M9K territory); module left untouched\n");
				return 0;
			}
			Pass::call_on_module(design, mod, "memory_map");
			log("  stage G: dissolved the module's constant async ROM(s) into mux "
			    "trees (the flow's own map_ffram memory_map expands the same shape)\n");
		}


		std::map<SigBit, Cell *> drv;
		for (Cell *c : mod->cells())
			if (c->hasPort(ID::Y))
				for (SigBit b : c->getPort(ID::Y))
					if (b.wire != nullptr)
						drv[b] = c;


		std::map<SigBit, SigBit> inv_of;
		auto get_inv = [&](SigBit g) -> SigBit {
			auto it = inv_of.find(g);
			if (it != inv_of.end())
				return it->second;
			Wire *w = mod->addWire(NEW_ID, 1);
			mod->addNot(NEW_ID, g, SigSpec(w));
			newcells++;
			inv_of[g] = SigBit(w);
			return SigBit(w);
		};


		auto clear_bit = [&](SigBit dbit, SigBit &g, SigBit &f) -> bool {
			if (dbit.wire == nullptr)
				return false;
			auto it = drv.find(dbit);
			if (it == drv.end() || it->second->type != ID($mux))
				return false;
			Cell *m = it->second;
			SigSpec A = m->getPort(ID::A), B = m->getPort(ID::B), S = m->getPort(ID::S);
			if (GetSize(S) != 1 || S[0].wire == nullptr)
				return false;
			int off = -1;
			SigSpec Yv = m->getPort(ID::Y);
			for (int k = 0; k < GetSize(Yv); k++)
				if (Yv[k] == dbit) { off = k; break; }
			if (off < 0 || off >= GetSize(A) || off >= GetSize(B))
				return false;
			if (A[off].wire != nullptr || A[off].data != State::S0)
				return false;
			if (B[off].wire == nullptr)
				return false;
			g = S[0];
			f = B[off];
			return true;
		};


		auto mk_dffeas = [&](SigBit d, SigBit q, SigBit clk, SigBit ena,
		                     SigBit clrn, SigBit sclr, State initial) {
			Cell *c = mod->addCell(NEW_ID, ID(dffeas));
			c->parameters[ID(is_wysiwyg)] = Const(std::string("TRUE"));
			c->parameters[ID(power_up)] = Const(std::string(initial == State::S1 ? "high" : "low"));
			c->setPort(ID(q), q);
			c->setPort(ID(d), d);
			c->setPort(ID(clk), clk);
			c->setPort(ID(ena), ena);
			c->setPort(ID(clrn), clrn);
			c->setPort(ID(prn), Const(State::S1, 1));
			c->setPort(ID(aload), Const(State::S0, 1));
			c->setPort(ID(asdata), Const(State::S0, 1));
			c->setPort(ID(sclr), sclr);
			c->setPort(ID(sload), Const(State::S0, 1));
			newcells++;
		};


		std::vector<Cell *> ffs;
		for (Cell *c : mod->cells())
			if (c->type == ID($adff) || c->type == ID($dff))
				ffs.push_back(c);

		int n = 0;
		for (Cell *c : ffs) {
			bool is_adff = c->type == ID($adff);
			int w = c->parameters[ID(WIDTH)].as_int();
			if (w < 1 || c->parameters[ID(CLK_POLARITY)].as_int() != 1)
				continue;
			SigSpec D = c->getPort(ID(D)), Q = c->getPort(ID(Q));
			if (GetSize(D) != w || GetSize(Q) != w)
				continue;

			if (!positive_ff(c, init_sigmap))
				continue;
			SigBit clk = c->getPort(ID(CLK))[0];
			if (clk.wire == nullptr)
				continue;

			struct BitPlan {
				int kind;
				SigBit d;
				SigBit q;
				SigBit ena;
				SigBit clrn;
				SigBit gate;
				bool has_gate;
			};
			std::vector<BitPlan> plan;
			bool all_ok = true;


			if (is_adff) {


				Const rv;
				if (c->parameters.count(ID(ARST_VALUE)))
					rv = c->parameters[ID(ARST_VALUE)];
				else if (c->parameters.count(ID(RESET_VALUE)))
					rv = c->parameters[ID(RESET_VALUE)];
				if (GetSize(rv) != w)
					continue;
				SigSpec AR = c->getPort(ID(ARST));
				if (GetSize(AR) != 1 || AR[0].wire == nullptr)
					continue;
				if (c->parameters[ID(ARST_POLARITY)].as_int() != 0)
					continue;
				SigBit rst = AR[0];
				for (int i = 0; i < w && all_ok; i++) {
					if (rv[i] == State::S0) {
						SigBit g, f;
						if (!clear_bit(D[i], g, f)) { all_ok = false; break; }
						plan.push_back({0, f, Q[i], SigBit(State::S1), rst, g, true});
					} else if (rv[i] == State::S1) {


						plan.push_back({2, D[i], Q[i], SigBit(State::S1), rst, SigBit(),
						                false});
					} else {
						all_ok = false;
					}
				}
			} else {

				SigBit s;
				for (int i = 0; i < w && all_ok; i++) {
					if (D[i].wire == nullptr) { all_ok = false; break; }
					auto it = drv.find(D[i]);
					if (it == drv.end() || it->second->type != ID($mux)) { all_ok = false; break; }
					Cell *m = it->second;
					SigSpec A = m->getPort(ID::A), B = m->getPort(ID::B), S = m->getPort(ID::S);
					if (GetSize(S) != 1 || S[0].wire == nullptr) { all_ok = false; break; }
					int off = -1;
					SigSpec Yv = m->getPort(ID::Y);
					for (int k = 0; k < GetSize(Yv); k++)
						if (Yv[k] == D[i]) { off = k; break; }
					if (off < 0 || off >= GetSize(A) || off >= GetSize(B)) { all_ok = false; break; }
					if (A[off].wire == nullptr || A[off] != Q[i]) { all_ok = false; break; }
					if (B[off].wire == nullptr) { all_ok = false; break; }
					if (i == 0) {
						s = S[0];
					} else if (s != S[0]) {
						all_ok = false;
						break;
					}
					SigBit g, f;
					SigBit dval = B[off];
					bool has_gate = clear_bit(dval, g, f);
					if (has_gate)
						dval = f;
					plan.push_back({1, dval, Q[i], s, SigBit(State::S1), g, has_gate});
				}
			}
			if (!all_ok || plan.empty() || GetSize(plan) != w)
				continue;

			for (auto &bp : plan) {


				SigBit sclr = bp.has_gate ? get_inv(bp.gate) : SigBit(State::S0);
				if (bp.kind == 2) {
					Wire *dn = mod->addWire(NEW_ID, 1);
					mod->addNot(NEW_ID, bp.d, SigSpec(dn));
					Wire *qn = mod->addWire(NEW_ID, 1);
					Wire *qo = mod->addWire(NEW_ID, 1);
					mod->addNot(NEW_ID, SigBit(qn), SigSpec(qo));
					State initial = initvals(bp.q);
					initvals.remove_init(bp.q);
					State inverted = initial == State::S0 ? State::S1 : initial == State::S1 ? State::S0 : State::Sx;
					mk_dffeas(SigBit(dn), SigBit(qn), clk, bp.ena, bp.clrn, sclr, inverted);

					mod->connect(bp.q, SigBit(qo));
					newcells += 2;
				} else {
					State initial = initvals(bp.q);
					initvals.remove_init(bp.q);
					mk_dffeas(bp.d, bp.q, clk, bp.ena, bp.clrn, sclr, initial);
				}
			}
			mod->remove(c);
			n += w;
		}
		if (n)
			log("  stage G: promoted %d FF bit(s) onto dffeas ENA/CLRN/SCLR pins\n", n);
		return n;
	}


	int rewrite_stage_ab(Module *mod, int &newcells, int &rewritten, int &paired_cells,
	                     int &skipped, int min_shift, bool naive_enabled = false, int min_arms = 1)
	{
		int fired = 0;

		std::map<SigBit, Cell *> drv;
		std::set<SigBit> ambiguous_drv;
		for (Cell *c : mod->cells()) {
			if (!c->hasPort(ID::Y))
				continue;
			for (SigBit b : c->getPort(ID::Y))
				if (b.wire != nullptr) {
					auto it = drv.find(b);
					if (it != drv.end()) {
						ambiguous_drv.insert(b);
						continue;
					}
					drv.emplace(b, c);
				}
		}


		std::vector<Cell *> cands;
		for (Cell *c : mod->cells())
			if (c->type == ID($pmux))
				cands.push_back(c);

		std::vector<Cand> qualified;
		for (Cell *c : cands) {
			SigSpec S = c->getPort(ID::S);
			SigSpec Bp = c->getPort(ID::B);
			SigSpec Y = c->getPort(ID::Y);
			int w = GetSize(Y), sw = GetSize(S);
			if (w <= 0 || sw < 2 || sw < min_arms || GetSize(Bp) != w * sw || !c->hasPort(ID::A)) {
				skipped++;
				log("  skip %s: ports/width (sw=%d < %d)\n", log_id(c->name), sw, min_arms);
				continue;
			}
			SigSpec A = c->getPort(ID::A);
			if (GetSize(A) != w) {
				skipped++;
				log("  skip %s: A width\n", log_id(c->name));
				continue;
			}
			std::vector<std::pair<int, SigSpec>> arms;
			SigSpec ref;
			bool ok = true;
			for (int i = 0; i < sw && ok; i++) {
				if (ambiguous_drv.count(S[i])) {
					ok = false;
					break;
				}
				auto it = drv.find(S[i]);
				if (it == drv.end()) {
					ok = false;
					break;
				}
				Cell *e = it->second;
				int code = -1;
				if (e->type == ID($eq) && e->hasPort(ID::A) && e->hasPort(ID::B)) {

					SigSpec ea = e->getPort(ID::A), eb = e->getPort(ID::B);
					if (GetSize(ea) != GetSize(eb) || GetSize(ea) == 0) {
						ok = false;
						break;
					}
					if (!const_uint(eb, code)) {
						ok = false;
						break;
					}
					if (ref.empty())
						ref = ea;
					else if (ref != ea) {
						ok = false;
						break;
					}
				} else if (e->type == ID($logic_not)) {

					SigSpec na = e->getPort(ID::A);
					SigSpec base = na;
					if (GetSize(na) == 1 && na[0].wire != nullptr) {
						auto rit = drv.find(na[0]);
						if (rit != drv.end() && rit->second->type == ID($reduce_or))
							base = rit->second->getPort(ID::A);
					}
					if (ref.empty())
						ref = base;
					if (base != ref || GetSize(base) == 0 || GetSize(base) > 31) {
						ok = false;
						break;
					}
					code = 0;
				} else {
					ok = false;
					break;
				}
				if (code < 0) {
					ok = false;
					break;
				}
				arms.push_back(std::make_pair(code, Bp.extract(i * w, w)));
			}
			if (!ok || ref.empty() || (int)arms.size() != sw) {
				skipped++;
				log("  skip %s: S decoder structure\n", log_id(c->name));
				continue;
			}
			std::map<int, int> seen;
			for (auto &a : arms)
				if (++seen[a.first] > 1) {
					ok = false;
					break;
				}
			if (!ok) {
				skipped++;
				log("  skip %s: duplicate codes\n", log_id(c->name));
				continue;
			}
			int needs = 0;
			for (auto &a : arms) {


				while (needs < 31 && (uint64_t(1) << needs) <= uint64_t(a.first))
					needs++;
			}
			if (needs < 1 || GetSize(ref) != needs) {
				skipped++;
				log("  skip %s: |W|=%d but codes need %d bits\n", log_id(c->name),
				    GetSize(ref), needs);
				continue;
			}
			Cand cd;
			cd.c = c;
			cd.S = S;
			cd.A = A;
			cd.Y = Y;
			cd.ref = ref;
			cd.w = w;
			cd.sw = sw;
			cd.nbits = needs;
			for (auto &a : arms)
				cd.arm[a.first] = a.second;
			qualified.push_back(cd);
		}


		std::map<std::string, std::vector<int>> sgroups;
		for (int i = 0; i < (int)qualified.size(); i++) {
			std::string key;
			for (auto b : qualified[i].S) {
				if (b.wire)
					key += b.wire->name.str() + "[" + std::to_string(b.offset) + "];";
				else
					key += "c" + std::to_string(b.data) + ";";
			}
			sgroups[key].push_back(i);
		}

		for (auto &g : sgroups) {
			std::vector<int> &idx = g.second;
			if (idx.size() < 2)
				continue;
			bool handled = false;
			int n = qualified[idx[0]].nbits;

			for (int shift = n - 2; shift >= min_shift && !handled; shift--) {
				int pw = n - shift;
				if (pw >= 31)
					continue;
				int n_pairs = int(uint32_t(1) << pw);
				if (n_pairs < 2 || n_pairs > 64)
					continue;
				for (int a = 0; a < (int)idx.size() && !handled; a++) {
					for (int b = a + 1; b < (int)idx.size() && !handled; b++) {
						Cand &c0 = qualified[idx[a]];
						Cand &c1 = qualified[idx[b]];
						if (c0.consumed || c1.consumed)
							continue;
						if (c0.nbits != n || c1.w != c0.w)
							continue;
						bool cover = true;
						if (n >= 31)
							continue;
						for (int code = 1; code < int(uint32_t(1) << n) && cover; code++)
							if (c0.arm.find(code) == c0.arm.end() ||
								c1.arm.find(code) == c1.arm.end())
								cover = false;
						if (!cover)
							continue;

						SigSpec st0, st1;
						std::vector<SigSpec> n0, s0, n1, s1;
						if (!collect_leaves(c0, shift, n_pairs, n0, s0, st0) ||
							!collect_leaves(c1, shift, n_pairs, n1, s1, st1))
							continue;
						bool swapped = true;
						for (int p = 1; p < n_pairs && swapped; p++)
							if (!(n0[p] == s1[p]) || !(s0[p] == n1[p]))
								swapped = false;
						if (!swapped)
							continue;


						std::string nm0 = log_id(c0.c->name), nm1 = log_id(c1.c->name);
						bool share = (shift == 1) && (c0.ref == c1.ref);
						SigSpec t0_no, t0_sw, t1_no, t1_sw;
						if (share) {


							std::vector<SigSpec> bank_no = s1, bank_sw = s0;
							bank_no[0] = mux_on(c0.ref[0], st0, s1[0], mod, newcells);
							bank_sw[0] = mux_on(c0.ref[0], st1, s0[0], mod, newcells);
							t0_no = build_tree(bank_no, 0, n_pairs, n - 1, c0.ref, mod, newcells);
							t0_sw = build_tree(bank_sw, 0, n_pairs, n - 1, c0.ref, mod, newcells);
							t1_no = t0_sw;
							t1_sw = t0_no;
						} else {
							t0_no = build_tree(n0, 0, n_pairs, n - 1, c0.ref, mod, newcells);
							t0_sw = build_tree(s0, 0, n_pairs, n - 1, c0.ref, mod, newcells);
							t1_no = build_tree(n1, 0, n_pairs, n - 1, c1.ref, mod, newcells);
							t1_sw = build_tree(s1, 0, n_pairs, n - 1, c1.ref, mod, newcells);
						}
						for (Cand *cd : {&c0, &c1}) {
							bool is0 = (cd == &c0);
							Cell *m = mod->addCell(NEW_ID, ID($mux));
							m->setParam(ID(WIDTH), cd->w);
							m->setPort(ID::A, is0 ? t0_no : t1_no);
							m->setPort(ID::B, is0 ? t0_sw : t1_sw);
							m->setPort(ID::S, cd->ref[shift - 1]);
							Wire *y = mod->addWire(NEW_ID, cd->w);
							m->setPort(ID::Y, y);
							newcells++;
							SigSpec res = y;
							mod->remove(cd->c);
							mod->connect(cd->Y, res);
							cd->consumed = true;
							rewritten++;
						}
						log("  pair: %s + %s (n=%d shift=%d %s trees)\n", nm0.c_str(),
							    nm1.c_str(), n, shift, share ? "shared" : "per-cell");
						paired_cells += 2;
						fired += 2;
						handled = true;
					}
				}
			}
		}


		if (min_shift <= 1 && naive_enabled) {
			for (auto &cd : qualified) {
				if (cd.consumed)
					continue;
				std::vector<std::pair<int, SigSpec>> arms;
				for (auto &a : cd.arm)
					arms.push_back(a);
				SigSpec root = build_arms_tree(arms, cd.ref, cd.nbits - 1, cd.A, mod, newcells);
				mod->remove(cd.c);
				mod->connect(cd.Y, root);
				rewritten++;
			}
		}
		return fired;
	}


	static bool eq_decode_of(SigBit s, const std::map<SigBit, Cell *> &drv,
	                         SigSpec &ref, int &code)
	{
		Cell *e = (s.wire != nullptr && drv.count(s)) ? drv.at(s) : nullptr;
		if (!e || e->type != ID($eq) || !e->hasPort(ID::A) || !e->hasPort(ID::B))
			return false;
		SigSpec a = e->getPort(ID::A), b = e->getPort(ID::B);
		if (GetSize(a) != GetSize(b) || GetSize(a) < 2 || GetSize(a) > 31)
			return false;
		if (b.is_fully_const() && !a.is_fully_const()) {
			ref = a;
			code = b.as_int(false);
		} else if (a.is_fully_const() && !b.is_fully_const()) {
			ref = b;
			code = a.as_int(false);
		} else {
			return false;
		}
		return true;
	}


	bool compute_arm_fold(Cell *c, const std::map<SigBit, Cell *> &drv,
	                      int idx, SigSpec &outB)
	{
		SigSpec S = c->getPort(ID::S), B = c->getPort(ID::B), Y = c->getPort(ID::Y);
		int w = GetSize(Y), sw = GetSize(S);
		if (w <= 0 || sw < 1 || GetSize(B) != w * sw)
			return false;
		SigSpec ref;
		int code = -1;
		if (!eq_decode_of(S[idx], drv, ref, code))
			return false;
		std::map<SigBit, int> pos;
		for (int p = 0; p < GetSize(ref); p++) {
			if (ref[p].wire == nullptr)
				return false;
			if (!pos.count(ref[p]))
				pos[ref[p]] = p;
		}
		SigSpec nb = B;
		bool any = false;
		for (int j = 0; j < w; j++) {
			SigBit b = B[idx * w + j];
			if (b.wire == nullptr)
				continue;
			auto it = pos.find(b);
			if (it == pos.end())
				return false;
			nb[idx * w + j] = SigBit((((unsigned)code >> it->second) & 1) != 0);
			any = true;
		}
		if (!any)
			return false;
		outB = nb;
		return true;
	}


	bool fold_arm(Cell *c, const std::map<SigBit, Cell *> &drv)
	{
		if (!c->hasPort(ID::S) || !c->hasPort(ID::B) || !c->hasPort(ID::Y))
			return false;
		int sw = GetSize(c->getPort(ID::S));
		int folded_arms = 0;
		for (int idx = 0; idx < sw; idx++) {
			SigSpec nb;
			if (!compute_arm_fold(c, drv, idx, nb))
				continue;
			c->setPort(ID::B, nb);
			folded_arms++;
		}
		return folded_arms > 0;
	}

	int rewrite_sparse_arms(Module *mod)
	{
		std::map<SigBit, Cell *> drv;
		for (Cell *c : mod->cells()) {
			if (c->type != ID($eq) || !c->hasPort(ID::Y))
				continue;
			for (SigBit b : c->getPort(ID::Y))
				if (b.wire != nullptr)
					drv[b] = c;
		}
		std::vector<Cell *> todo;
		for (Cell *c : mod->cells())
			if (c->type == ID($pmux) || c->type == ID($mux))
				todo.push_back(c);
		int n = 0;
		for (Cell *c : todo)
			if (fold_arm(c, drv))
				n++;
		return n;
	}


	bool legacy_rules_cannot_match(Module *mod)
	{
		if (!do_rewrite || !general_mux_enabled || !no_probe || preopt ||
		    naive_enabled || counter_enabled || !no_decode_share ||
		    !no_hold_extract || (!no_sclr_promo && !sclr_promo_rom_only))
			return false;
		int min_width;
		if (!small_data_selectors(mod, min_width))
			return false;

		SigMap sigmap(mod);
		std::map<SigBit, Cell *> drivers;
		std::vector<Cell *> muxes;
		for (Cell *c : mod->cells()) {
			if (c->hasPort(ID::Y))
				for (SigBit b : c->getPort(ID::Y)) {
					if (b.wire == nullptr)
						continue;
					if (!drivers.emplace(b, c).second)
						return false;
				}
			if (c->type.in(ID($mux), ID($pmux)))
				muxes.push_back(c);
		}


		auto reference_of = [&](SigBit s, SigSpec &ref) -> bool {
			auto it = drivers.find(s);
			if (it == drivers.end())
				return false;
			Cell *c = it->second;
			if (c->type == ID($eq) && c->hasPort(ID::A) && c->hasPort(ID::B)) {
				SigSpec a = sigmap(c->getPort(ID::A));
				SigSpec b = sigmap(c->getPort(ID::B));
				if (a.is_fully_def() && !b.is_fully_const())
					std::swap(a, b);
				if (GetSize(a) != GetSize(b) || !b.is_fully_def() || a.is_fully_const())
					return false;
				ref = a;
			} else if (c->type == ID($logic_not) && c->hasPort(ID::A)) {
				ref = sigmap(c->getPort(ID::A));
			} else {
				return false;
			}
			if (GetSize(ref) < 2 || GetSize(ref) > 3)
				return false;
			std::set<SigBit> unique;
			for (SigBit b : ref)
				if (b.wire == nullptr || !b.wire->port_input || !unique.insert(b).second)
					return false;
			return true;
		};

		std::set<SigBit> pmux_reference_bits, all_reference_bits;
		for (Cell *c : muxes) {
			if (!c->hasPort(ID::S) || !c->hasPort(ID::A) ||
			    !c->hasPort(ID::B) || !c->hasPort(ID::Y))
				return false;
			SigSpec ref;
			bool direct_eq = false;
			for (SigBit s : c->getPort(ID::S)) {
				auto it = drivers.find(s);
				Cell *d = it == drivers.end() ? nullptr : it->second;
				if (c->type == ID($pmux) || (d && d->type == ID($eq))) {
					SigSpec r;
					if (!reference_of(s, r))
						return false;
					if (c->type == ID($pmux) && !ref.empty() && ref != r)
						return false;
					ref = r;
					for (SigBit b : r)
						all_reference_bits.insert(b);
				}
				direct_eq = direct_eq || (d && d->type == ID($eq));
			}
			if (c->type == ID($pmux)) {


				if (!direct_eq || ref.empty())
					return false;


				for (SigBit b : ref)
					if (!pmux_reference_bits.insert(b).second)
						return false;
			}
		}


		for (Cell *c : muxes)
			for (IdString port : {ID::A, ID::B})
				for (SigBit b : sigmap(c->getPort(port)))
					if (all_reference_bits.count(b))
						return false;


		if (!no_prio_or)
			for (Cell *start : muxes) {
				if (start->type != ID($mux))
					continue;
				Cell *cur = start;
				std::set<Cell *> seen;
				int length = 0;
				while (cur && cur->type == ID($mux)) {
					if (!seen.insert(cur).second)
						return false;
					SigSpec s = cur->getPort(ID::S);
					if (GetSize(s) != 1 || s[0].wire == nullptr)
						break;
					auto sd = drivers.find(s[0]);
					if (sd != drivers.end() && sd->second->type == ID($eq))
						break;
					if (++length >= 3)
						return false;
					SigSpec a = cur->getPort(ID::A);
					if (a.empty() || a[0].wire == nullptr)
						break;
					auto next = drivers.find(a[0]);
					cur = next == drivers.end() ? nullptr : next->second;
				}
			}
		return true;
	}

	bool small_data_selectors(Module *mod, int &min_width)
	{
		if (mod->get_bool_attribute(ID::keep))
			return false;
		SigMap sigmap(mod);


		pool<SigBit> select_bits;
		for (Cell *c : mod->cells())
			if (c->type == ID($pmux))
				for (SigBit bit : sigmap(c->getPort(ID::S)))
					select_bits.insert(bit);
		if (select_bits.empty())
			return false;
		dict<SigBit, Cell *> drivers;
		pool<SigBit> multiple_drivers;
		for (Cell *c : mod->cells()) {
			if (c->get_bool_attribute(ID::keep) || c->type.str().find("$mem") == 0)
				return false;
			if (c->hasPort(ID::Y))
				for (SigBit b : sigmap(c->getPort(ID::Y))) {
					if (!select_bits.count(b))
						continue;
					if (drivers.count(b) && drivers[b] != c)
						multiple_drivers.insert(b);
					drivers[b] = c;
				}
		}
		int count = 0;
		min_width = INT_MAX;
		for (Cell *c : mod->cells()) {
			if (c->type != ID($pmux))
				continue;
			if (c->get_bool_attribute(ID::keep))
				return false;
			SigSpec S = sigmap(c->getPort(ID::S));
			SigSpec B = sigmap(c->getPort(ID::B));
			int w = GetSize(c->getPort(ID::Y));
			if (w < 2 || GetSize(S) < 2 || GetSize(B) != w * GetSize(S))
				return false;
			SigSpec ref;
			std::set<int> codes;
			int variable = 0;
			for (SigBit b : B)
				variable += b.wire != nullptr;
			if (variable < w)
				return false;
			for (SigBit s : S) {
				if (multiple_drivers.count(s))
					return false;
				auto it = drivers.find(s);
				if (it == drivers.end())
					return false;
				Cell *d = it->second;
				if (!d->hasPort(ID::Y) || sigmap(d->getPort(ID::Y)) != SigSpec(s))
					return false;
				SigSpec r;
				int code = -1;
				if (d->type == ID($eq)) {
					SigSpec a = sigmap(d->getPort(ID::A)), b = sigmap(d->getPort(ID::B));
					if (a.is_fully_def() && !b.is_fully_const())
						std::swap(a, b);
					if (!b.is_fully_def() || a.is_fully_const() || GetSize(a) != GetSize(b))
						return false;
					r = a;
					code = b.as_int(false);
				} else if (d->type == ID($logic_not)) {
					r = sigmap(d->getPort(ID::A));
					code = 0;
				} else {
					return false;
				}
				if (GetSize(r) < 2 || GetSize(r) > 3 || (!ref.empty() && ref != r) || !codes.insert(code).second)
					return false;
				ref = r;
			}
			if (GetSize(S) < (1 << GetSize(ref)) - 1)
				return false;
			count++;
			min_width = std::min(min_width, w);
		}
		return count > 0;
	}

	bool reconvergent_mux_data(Module *mod)
	{
		SigMap sigmap(mod);
		std::map<SigSpec, int> uses;
		std::set<SigSpec> outputs;
		for (Cell *c : mod->cells())
			if (c->type.in(ID($mux), ID($pmux)))
				outputs.insert(sigmap(c->getPort(ID::Y)));
		for (Cell *c : mod->cells()) {
			if (!c->type.in(ID($mux), ID($pmux)))
				continue;
			int w = GetSize(c->getPort(ID::Y));
			if (w <= 0 || !c->hasPort(ID::A) || !c->hasPort(ID::B))
				continue;
			SigSpec A = sigmap(c->getPort(ID::A)), B = sigmap(c->getPort(ID::B));
			if (outputs.count(A) && ++uses[A] > 1)
				return true;
			for (int i = 0; i + w <= GetSize(B); i += w) {
				SigSpec b = B.extract(i, w);
				if (outputs.count(b) && ++uses[b] > 1)
					return true;
			}
		}
		return false;
	}


	int rewrite_uniform_operators(Module *mod, int &newcells)
	{
		bool has_operator = false;
		for (Cell *c : mod->cells())
			has_operator = has_operator || c->type.in(ID($add), ID($sub));
		if (!has_operator)
			return 0;
		SigMap sigmap(mod);
		dict<SigBit, Cell *> driver;
		pool<SigBit> ambiguous;
		pool<SigBit> external_drivers;
		dict<SigBit, int> users;
		for (Wire *w : mod->wires()) {
			if (w->port_output)
				for (SigBit b : sigmap(SigSpec(w))) users[b]++;
			if (w->port_input)
				for (SigBit b : sigmap(SigSpec(w))) external_drivers.insert(b);
		}
		for (Cell *c : mod->cells()) {
			for (auto &p : c->connections())
				if (c->output(p.first))
					for (SigBit bit : sigmap(p.second)) {
						if (bit.wire == nullptr) continue;
						if (external_drivers.count(bit) || (driver.count(bit) && driver[bit] != c))
							ambiguous.insert(bit);
						driver[bit] = c;
					}
			for (auto &p : c->connections())
				if (c->input(p.first))
					for (SigBit b : sigmap(p.second)) users[b]++;
		}
		std::vector<Cell *> muxes;
		for (Cell *c : mod->cells())
			if (c->type == ID($pmux)) muxes.push_back(c);
		int count = 0;
		for (Cell *m : muxes) {
			int width = GetSize(m->getPort(ID::Y));
			int arms = GetSize(m->getPort(ID::S));
			if (!m->hasPort(ID::A) || !m->hasPort(ID::B) || width <= 0 ||
			    GetSize(m->getPort(ID::A)) != width || GetSize(m->getPort(ID::B)) != arms*width) continue;
			std::set<SigBit> root_bits;
			for (SigBit bit : sigmap(m->getPort(ID::Y))) root_bits.insert(bit);
			if (width < 4 || arms < 3 || m->get_bool_attribute(ID::keep)) continue;
			std::vector<Cell *> ops;
			std::vector<SigSpec> a, b;
			bool ok = true;


			std::set<SigBit> active_bits, safe_bits;
			for (int i = -1; i < arms; i++) {
				SigSpec data = sigmap(i < 0 ? m->getPort(ID::A) : m->getPort(ID::B).extract(i*width,width));
				auto it = driver.find(data[0]);
				if (it == driver.end()) { ok = false; break; }
				Cell *op = it->second;
				if (!op->hasPort(ID::Y) || !op->hasPort(ID::A) || !op->hasPort(ID::B) ||
				    sigmap(op->getPort(ID::Y)) != data ||
				    !op->hasParam(ID::A_WIDTH) || !op->hasParam(ID::B_WIDTH) || !op->hasParam(ID::Y_WIDTH) ||
				    !op->hasParam(ID::A_SIGNED) || !op->hasParam(ID::B_SIGNED) ||
				    op->getParam(ID::A_WIDTH).as_int() != GetSize(op->getPort(ID::A)) ||
				    op->getParam(ID::B_WIDTH).as_int() != GetSize(op->getPort(ID::B)) ||
				    op->getParam(ID::Y_WIDTH).as_int() != width ||
				    GetSize(op->getPort(ID::A)) < 1 || GetSize(op->getPort(ID::B)) < 1 ||
				    !op->getParam(ID::A_SIGNED).is_fully_def() || !op->getParam(ID::B_SIGNED).is_fully_def() ||
				    !op->type.in(ID($add), ID($sub)) || op->get_bool_attribute(ID::keep) ||
				    (!ops.empty() && (op->type != ops[0]->type || op->parameters != ops[0]->parameters))) { ok = false; break; }
				for (SigBit bit : data)
					if (bit.wire == nullptr || ambiguous.count(bit) || users[bit] != 1) ok = false;
				if (!ok) break;

				auto safe_input = [&](auto &&self, SigBit bit) -> bool {
					if (bit.wire == nullptr) return true;
					if (ambiguous.count(bit) || root_bits.count(bit)) return false;
					if (safe_bits.count(bit)) return true;
					if (!active_bits.insert(bit).second) return false;
					auto di = driver.find(bit);
					if (di != driver.end()) {
						Cell *d = di->second;
						bool stateful = d->type.in(ID($dff), ID($dffe), ID($adff), ID($adffe), ID($sdff), ID($sdffe), ID($sdffce), ID($dlatch), ID($adlatch));
						if (!stateful) {
							if (d->type.str().empty() || d->type.str()[0] != '$') return false;
							for (auto &port : d->connections())
								if (d->input(port.first))
									for (SigBit input : sigmap(port.second))
										if (!self(self, input)) return false;
						}
					}
					active_bits.erase(bit);
					safe_bits.insert(bit);
					return true;
				};
				for (IdString port : {ID::A, ID::B})
					for (SigBit input : sigmap(op->getPort(port)))
						if (!safe_input(safe_input, input)) ok = false;
				for (SigBit input : sigmap(m->getPort(ID::S)))
					if (!safe_input(safe_input, input)) ok = false;
				if (!ok) break;
				ops.push_back(op);
				a.push_back(sigmap(op->getPort(ID::A)));
				b.push_back(sigmap(op->getPort(ID::B)));
			}
			if (!ok || ops.size() != size_t(arms+1)) continue;
			SigSpec aa, bb;
			for (int i=1; i<=arms; i++) {aa.append(a[i]);bb.append(b[i]);}
			Wire *ay = mod->addWire(NEW_ID,GetSize(a[0]));
			Wire *by = mod->addWire(NEW_ID,GetSize(b[0]));
			Cell *am = mod->addPmux(NEW_ID,a[0],aa,m->getPort(ID::S),ay);
			Cell *bm = mod->addPmux(NEW_ID,b[0],bb,m->getPort(ID::S),by);
			Cell *shared = mod->addCell(NEW_ID,ops[0]->type);
			shared->parameters = ops[0]->parameters;
			shared->setPort(ID::A,ay);shared->setPort(ID::B,by);
			shared->setPort(ID::Y,m->getPort(ID::Y));
			for (SigBit bit : sigmap(SigSpec(ay))) driver[bit] = am;
			for (SigBit bit : sigmap(SigSpec(by))) driver[bit] = bm;
			for (SigBit bit : sigmap(m->getPort(ID::Y))) driver[bit] = shared;
			mod->remove(m);
			count++;newcells+=3;
		}
		return count;
	}


	bool deep_independent_selection(Module *mod)
	{
		SigMap sigmap(mod);
		std::map<SigSpec, Cell *> nodes;
		for (Cell *c : mod->cells()) {
			if (!c->type.in(ID($pmux), ID($mux)) || !c->hasPort(ID::A) ||
			    !c->hasPort(ID::B) || !c->hasPort(ID::S) || !c->hasPort(ID::Y)) continue;
			int w = GetSize(c->getPort(ID::Y));
			int arms = c->type == ID($pmux) ? GetSize(c->getPort(ID::S)) : 1;
			if (w < 1 || arms < 1 || GetSize(c->getPort(ID::A)) != w ||
			    GetSize(c->getPort(ID::B)) != w*arms) continue;
			nodes[sigmap(c->getPort(ID::Y))] = c;
		}
		std::map<SigSpec, int> known;
		std::set<SigSpec> active;
		auto depth = [&](auto &&self, const SigSpec &signal) -> int {
			if (known.count(signal)) return known[signal];
			auto it = nodes.find(signal);
			if (it == nodes.end()) return 0;
			if (!active.insert(signal).second) return 3;
			Cell *c = it->second;
			int width = GetSize(c->getPort(ID::Y));
			int longest = self(self,sigmap(c->getPort(ID::A)));
			SigSpec b = sigmap(c->getPort(ID::B));
			for (int i=0; i<GetSize(b); i+=width)
				longest = std::max(longest,self(self,b.extract(i,width)));
			active.erase(signal);
			return known[signal] = longest + (c->type == ID($pmux));
		};
		for (auto &entry : nodes)
			if (depth(depth,entry.first) >= 2) return true;
		return false;
	}

	int rewrite_general_mux(Design *design, Module *mod, int &newcells)
	{
		if (!design->selected_whole_module(mod))
			return 0;
		for (Wire *w : mod->wires())
			if (w->get_bool_attribute(ID::keep))
				return 0;
		int min_width;
		if (!small_data_selectors(mod, min_width))
			return 0;
		int flattened = 0;
		bool reconvergent = reconvergent_mux_data(mod);
		if (!reconvergent && deep_independent_selection(mod)) {
			int count = 0;
            for(int iteration=0;iteration<32;iteration++) {
                int changed = rewrite_nested_arithmetic(mod, newcells);
                if(!changed) break;
                count += changed;
                Pass::call_on_module(design, mod, "opt_clean");
            }
			log("  general-mux: deep independent selection, %d arithmetic group(s) shared in %s.\n", count, log_id(mod));
			if (count) return count;
		}
		if (reconvergent) {
			Pass::call_on_module(design, mod, "opt");
			flattened = rewrite_repeated_mux_paths(mod, newcells);
			if (flattened) {
				Pass::call_on_module(design, mod, "opt_clean");
				log("  general-mux: %d repeated-path root(s) merged in %s.\n", flattened, log_id(mod));
				return flattened;
			}
		}


		if (min_width >= 4)
			Pass::call_on_module(design, mod, "opt_share");
		rewrite_uniform_operators(mod, newcells);
		Pass::call_on_module(design, mod, "opt_clean");
		int tree_new = 0, tree_changed = 0, tree_paired = 0, tree_skipped = 0;
		rewrite_stage_ab(mod, tree_new, tree_changed, tree_paired, tree_skipped, 1, true, 1);
		newcells += tree_new;
		Pass::call_on_module(design, mod, "opt_clean");
		log("  general-mux: binary data selection applied in %s.\n", log_id(mod));
		return 1;
	}


	int rewrite_next_state(Module *mod, int &newcells)
	{
		std::map<SigBit, Cell *> drv;
		for (Cell *c : mod->cells()) {
			if (c->type != ID($eq) || !c->hasPort(ID::Y))
				continue;
			for (SigBit b : c->getPort(ID::Y))
				if (b.wire != nullptr)
					drv[b] = c;
		}
		std::vector<Cell *> todo;
		for (Cell *c : mod->cells())
			if (c->type == ID($pmux))
				todo.push_back(c);
		int n = 0;
		for (Cell *c : todo) {
			SigSpec S = c->getPort(ID::S), B = c->getPort(ID::B), Y = c->getPort(ID::Y);
			SigSpec A = c->hasPort(ID::A) ? c->getPort(ID::A) : SigSpec();
			int w = GetSize(Y), sw = GetSize(S);
			if (w < 3 || w > 20 || sw < 4 || GetSize(B) != w * sw || GetSize(A) != w)
				continue;
			int nb = w;
			SigSpec ref;
			std::map<int, int> code_of;
			bool ok = true;
			for (int i = 0; i < sw && ok; i++) {
				SigSpec r;
				int code = -1;
				if (!eq_decode_of(S[i], drv, r, code) || code < 0) {
					ok = false;
					break;
				}
				if (ref.empty())
					ref = r;
				else if (ref != r) {
					ok = false;
					break;
				}
				if (code >= int(uint32_t(1) << nb) || code_of.count(code)) {
					ok = false;
					break;
				}
				code_of[code] = i;
			}
			if (!ok || ref.empty() || GetSize(ref) != nb)
				continue;

			for (int code = 1; code < int(uint32_t(1) << nb) && ok; code++)
				if (!code_of.count(code))
					ok = false;
			if (!ok || GetSize(S) < 1)
				continue;
			std::map<int, SigSpec> arm;
			for (int code = 1; code < int(uint32_t(1) << nb) && ok; code++) {
				SigSpec d = B.extract(code_of[code] * w, w);
				if (!d.is_fully_const())
					ok = false;
				else
					arm[code] = d;
			}
			if (!ok)
				continue;
			std::vector<int> exc;
			int mask = int(uint32_t(1) << nb) - 1;
			for (int code = 1; code < int(uint32_t(1) << nb); code++)
				if (arm[code].as_int(false) != ((code + 1) & mask))
					exc.push_back(code);


			if ((int)exc.size() > 3 || 2 * (int)exc.size() >= int(uint32_t(1) << nb))
				continue;
			std::string nm = log_id(c->name);


			SigSpec one(State::S0, nb);
			one[0] = State::S1;
			Cell *ad = mod->addCell(NEW_ID, ID($add));
			ad->setParam(ID::A_WIDTH, nb);
			ad->setParam(ID::B_WIDTH, nb);
			ad->setParam(ID::Y_WIDTH, nb);
			ad->setPort(ID::A, ref);
			ad->setPort(ID::B, one);
			Wire *ay = mod->addWire(NEW_ID, nb);
			ad->setPort(ID::Y, ay);
			newcells++;
			SigSpec cur = ay;
			for (int code : exc) {
				Cell *m = mod->addCell(NEW_ID, ID($mux));
				m->setParam(ID(WIDTH), w);
				m->setPort(ID::A, cur);
				m->setPort(ID::B, arm[code]);
				m->setPort(ID::S, S[code_of[code]]);
				Wire *my = mod->addWire(NEW_ID, w);
				m->setPort(ID::Y, my);
				cur = my;
				newcells++;
			}


			bool zero_follows = A.is_fully_const() && A.as_int(false) == (1 & mask);
			if (!zero_follows) {
				SigSpec zsel;
				if (code_of.count(0)) {
					zsel = S[code_of[0]];
				} else {
					Wire *nz = mod->addWire(NEW_ID, 1);
					mod->addReduceOr(NEW_ID, ref, nz);
					Wire *z = mod->addWire(NEW_ID, 1);
					mod->addNot(NEW_ID, nz, z);
					zsel = z;
					newcells += 2;
				}
				Cell *m = mod->addCell(NEW_ID, ID($mux));
				m->setParam(ID(WIDTH), w);
				m->setPort(ID::A, cur);
				m->setPort(ID::B, A);
				m->setPort(ID::S, zsel);
				Wire *my = mod->addWire(NEW_ID, w);
				m->setPort(ID::Y, my);
				cur = my;
				newcells++;
			}
			mod->remove(c);
			mod->connect(Y, cur);
			n++;
			log("  counter: %s (%d bits, %d exception row(s)) -> $add + muxes\n",
			    nm.c_str(), nb, (int)exc.size());
		}
		return n;
	}


	bool can_plan_module_locally(RTLIL::Design *design, RTLIL::Module *mod)
	{


		for (Cell *cell : mod->cells())
			if (design->module(cell->type) != nullptr)
				return false;
		return true;
	}

	RTLIL::Design *clone_design(RTLIL::Design *d)
	{
		RTLIL::Design *c = new RTLIL::Design;
		for (auto m : d->modules())
			c->add(m->clone());
		return c;
	}


	void probe_pre(RTLIL::Design *d, int variant)
	{
		Pass::call(d, "opt_muxtree");
		Pass::call(d, "opt_merge -share_all");
		Pass::call(d, "opt_clean");
		if (variant != 2)
			return;
		Pass::call(d, "opt -nodffe -nosdff");
		Pass::call(d, "opt");
		Pass::call(d, "memory -nomap");
		Pass::call(d, "opt_clean");
		Pass::call(d, "opt -full");
		Pass::call(d, "opt_clean");
	}


	std::string design_digest(RTLIL::Design *d, const std::string &top_name)
	{
		RTLIL::Module *m = d->module(RTLIL::escape_id(top_name));
		if (!m)
			return std::string();
		std::vector<std::string> lines;
		for (auto c : m->cells()) {
			std::string s = c->name.str() + "|" + c->type.str();
			for (auto &p : c->parameters)
				s += ":" + p.first.str() + "=" + log_signal(p.second);
			for (auto &conn : c->connections())
				s += ";" + conn.first.str() + "=" + log_signal(conn.second);
			lines.push_back(s);
		}
		std::sort(lines.begin(), lines.end());
		std::string out;
		for (auto &l : lines)
			out += l + "\n";
		return out;
	}

	// Area selection through additional synthesis is unavailable in the contest
	// pass. Keep these failure-only helpers while the structural planning paths
	// retain their existing control flow. They cannot execute any mapper.
	int probe_luts_design(RTLIL::Design *, const std::string &)
	{
		log_cmd_error("Additional design synthesis is disabled; PMUX uses structural rules only.\n");
		return -1;
	}

	int probe_base_lut(RTLIL::Design *, const std::string &)
	{
		log_cmd_error("Additional design synthesis is disabled; PMUX uses structural rules only.\n");
		return -1;
	}


	inline static int invocation_depth = 0;

	struct DepthGuard {
		int &counter;
		bool const outer;
		explicit DepthGuard(int &c) : counter(c), outer(c == 0) { ++counter; }
		~DepthGuard() { --counter; }
	};

	void execute(std::vector<std::string> args, RTLIL::Design *design) override
	{
		DepthGuard depth_guard(invocation_depth);
		if (!depth_guard.outer) {
			log("PMUX_OPT_RTLIL: reentrant invocation skipped (pass depth %d); the outer "
			    "invocation owns this design.\n", invocation_depth);
			return;
		}
		log_header(design, "Executing PMUX_OPT_RTLIL pass.\n");
		do_rewrite = false;
		naive_enabled = false;
		general_mux_enabled = true;
		probe_all = false;
		no_prio_or = false;
		no_decode_share = true;
		wide_decode_share_enabled = true;
		no_sclr_promo = true;
		sclr_promo_rom_only = false;
		no_hold_extract = true;
		preopt = false;
		size_t argidx = 1;
		while (argidx < args.size()) {
			if (args[argidx] == "-no-general-mux") {
				general_mux_enabled = false;
				argidx++;
				continue;
			}
			if (args[argidx] == "-rewrite") {
				do_rewrite = true;
				argidx++;
				continue;
			}
			if (args[argidx] == "-counter") {
				log_cmd_error("-counter is unavailable: its area selection requires additional ABC calls.\n");
			}
			if (args[argidx] == "-naive") {
				naive_enabled = true;
				argidx++;
				continue;
			}
			if (args[argidx] == "-probe-all") {
				log_cmd_error("-probe-all is unavailable: additional ABC calls are not permitted.\n");
			}
			if (args[argidx] == "-no-probe") {
				argidx++;
				continue;
			}
			if (args[argidx] == "-no-prio-or") {
				no_prio_or = true;
				argidx++;
				continue;
			}
			if (args[argidx] == "-preopt") {
				preopt = true;
				argidx++;
				continue;
			}
			if (args[argidx] == "-no-decode-share" || args[argidx] == "-decode-share-off") {
				no_decode_share = true;
				wide_decode_share_enabled = false;
				argidx++;
				continue;
			}
			if (args[argidx] == "-no-sclr-promo" || args[argidx] == "-sclr-promo-off") {
				no_sclr_promo = true;
				argidx++;
				continue;
			}
			if (args[argidx] == "-decode-share") {
				no_decode_share = false;
				argidx++;
				continue;
			}
			if (args[argidx] == "-sclr-promo") {
				no_sclr_promo = false;
				argidx++;
				continue;
			}
			if (args[argidx] == "-sclr-promo-rom-only") {


				no_sclr_promo = false;
				sclr_promo_rom_only = true;
				argidx++;
				continue;
			}
			if (args[argidx] == "-no-hold-extract" || args[argidx] == "-hold-extract-off") {
				no_hold_extract = true;
				argidx++;
				continue;
			}
			if (args[argidx] == "-hold-extract") {
				no_hold_extract = false;
				argidx++;
				continue;
			}
			break;
		}
		extra_args(args, argidx, design);

		if (do_rewrite) {
			for (Module *mod : design->selected_modules()) {
				if (!design->selected_whole_module(mod)) {
					log("PMUX_OPT_RTLIL: rewrite skipped because module %s is only partially selected; "
					    "the design is unchanged.\n", log_id(mod));
					return;
				}
				bool protected_module = mod->get_bool_attribute(ID::keep);
				for (Wire *w : mod->wires())
					protected_module = protected_module || w->get_bool_attribute(ID::keep);
				for (Cell *c : mod->cells())
					protected_module = protected_module || c->get_bool_attribute(ID::keep);
				if (protected_module) {
					log("PMUX_OPT_RTLIL: rewrite skipped because module %s contains a keep attribute; "
					    "the design is unchanged.\n", log_id(mod));
					return;
				}
			}
		}

		int total = 0, multi = 0, rewritten = 0, paired_cells = 0, skipped = 0, newcells = 0;
		int prio_cells = 0, gate_skipped = 0, folded_cells = 0, ctr_cells = 0;
		int prio_or_chains = 0;
		int decode_pairs = 0, sclr_promoted = 0;
		int hold_extracted = 0;
		int general_transforms = 0;


		int probe_skipped = 0;


		bool any_fired = false;


		int gate_base_probes = 0, gate_plan_probes = 0, gate_plans_pruned = 0;

		if (do_rewrite) {
			if (preopt) {
				log("PMUX_OPT_RTLIL: -preopt normalisation prelude: running whole-design `opt` "
				    "before the candidate scan (the stage-E prio-or pattern only matches on the "
				    "post-opt design).\n");
				Pass::call(design, "opt");
			}

			struct Plan { Module *mod; int variant; bool use_c; bool use_d; bool use_fg; };
			std::vector<Plan> plans;


			int n_modules = 0;
			for ([[maybe_unused]] Module *cnt_m : design->selected_modules())
				n_modules++;
			bool fg_allowed = n_modules == 1;
			for (Module *mod : design->selected_modules()) {
				if (no_probe && !counter_enabled && !preopt && no_decode_share && no_hold_extract) {
					bool has_memory = false, has_pmux = false;
					for (Cell *cell : mod->cells()) {
						has_memory = has_memory || cell->type.str().find("$mem") == 0;
						has_pmux = has_pmux || cell->type == ID($pmux);
					}
					if (has_memory && !has_pmux) {
						SigMap init_sigmap(mod);
						bool eligible_ff = false;
						if (!no_sclr_promo)
							for (Cell *cell : mod->cells())
								eligible_ff = eligible_ff || positive_ff(cell, init_sigmap);
						if (!eligible_ff) {
							gate_skipped++;
							continue;
						}
					}
				}
				if (legacy_rules_cannot_match(mod)) {
					gate_skipped++;
					log("  general-mux: legacy patterns excluded structurally; clone skipped.\n");
					continue;
				}


				bool protected_module = mod->get_bool_attribute(ID::keep);
				for (Wire *w : mod->wires())
					protected_module = protected_module || w->get_bool_attribute(ID::keep);
				for (Cell *c : mod->cells())
					protected_module = protected_module || c->get_bool_attribute(ID::keep);
				if (no_probe && !counter_enabled && !preopt && !protected_module &&
				    design->selected_whole_module(mod)) {
					int module_changed = 0;
					int e_new = 0;
					int e_count = no_prio_or ? 0 : rewrite_priority_or_chains(mod, e_new);
					prio_or_chains += e_count;newcells += e_new;module_changed += e_count;
					int p_new = 0;
					int p_count = rewrite_priority_cells(mod, p_new);
					prio_cells += p_count;newcells += p_new;module_changed += p_count;


					std::unique_ptr<Module> unchanged;
					if (module_changed == 0) unchanged.reset(mod->clone());
					Pass::call_on_module(design, mod, "opt_muxtree");
					Pass::call_on_module(design, mod, "opt_merge -share_all");
					Pass::call_on_module(design, mod, "opt_clean");
					int a_new = 0, a_count = 0, a_pairs = 0, a_skipped = 0;
					rewrite_stage_ab(mod, a_new, a_count, a_pairs, a_skipped, 1, naive_enabled, 1);
					newcells += a_new;paired_cells += a_pairs;skipped += a_skipped;module_changed += a_count;
					bool has_memory = false;
					for (Cell *c : mod->cells())
						has_memory = has_memory || c->type.str().find("$mem") == 0;
					bool may_fg = fg_allowed && (!no_decode_share || !no_hold_extract ||
						(!no_sclr_promo && (!sclr_promo_rom_only || has_memory)));
					if (may_fg) {
						int h_count = no_hold_extract ? 0 : rewrite_hold_extract(mod, newcells);
						int f_count = no_decode_share ? 0 : rewrite_decode_share(mod, newcells);
						hold_extracted += h_count;decode_pairs += f_count;module_changed += h_count+f_count;
					}
					// Factor only comparisons wider than a Cyclone IV LUT here.
					// Four-bit data selectors retain their existing binary-selection path.
					if (no_decode_share && wide_decode_share_enabled) {
						int wide_count = rewrite_decode_share(mod, newcells, 5);
						decode_pairs += wide_count; module_changed += wide_count;
					}
					int c_count = rewrite_sparse_arms(mod);
					folded_cells += c_count;module_changed += c_count;
					if (may_fg) {
						int g_count = no_sclr_promo ? 0 : rewrite_sclr_promo(design, mod, newcells);
						sclr_promoted += g_count;module_changed += g_count;
					}
					rewritten += module_changed;
					any_fired = any_fired || module_changed > 0;
					if (module_changed == 0) {
						gate_skipped++;
						Module *original = unchanged.release();
						design->remove(mod);
						design->add(original);
						mod = original;
					}
					log("  structural mode: %s processed once, %d transformation(s).\n",log_id(mod),module_changed);
					continue;
				}
				std::string top_name = mod->name.str().substr(1);


				int base_lut = -1;
				bool base_tried = false, fired_seen = false;
				int best_after = -1, best_variant = 0, best_rw = 0;
				bool best_use_c = false, best_use_d = false, best_use_fg = false;


				std::vector<std::string> probed_digests;


				for (int cand : {1, 2, 3, 4}) {
					int variant = (cand <= 2) ? cand : cand - 2;
					bool use_c = (cand > 2);


					int t_new = 0, t_rw = 0, t_pr = 0, t_sk = 0, k_p = 0, k_c = 0;
					RTLIL::Design *d = nullptr;
					try {
						if (no_probe && can_plan_module_locally(design, mod)) {
							d = new RTLIL::Design;
							d->add(mod->clone());
						} else {
							d = clone_design(design);
						}
						RTLIL::Module *mx = d->module(RTLIL::escape_id(top_name));
						if (mx) {


							int k_e = no_prio_or ? 0 : rewrite_priority_or_chains(mx, t_new);
							k_p = rewrite_priority_cells(mx, t_new);
							probe_pre(d, variant);


							rewrite_stage_ab(mx, t_new, t_rw, t_pr, t_sk, 1,
							                 naive_enabled, 1);
							probe_skipped += t_sk;
							if (use_c)
								k_c = rewrite_sparse_arms(mx);


							int v_rw = t_rw + k_p + k_c + k_e;
							if (v_rw >= 1) {
								fired_seen = true;
								any_fired = true;
							}


					bool probe_it = v_rw >= 1 && !(use_c && k_c == 0) && !no_probe;
						if (no_probe) {


							if (v_rw >= 1 && best_variant == 0) {
								best_variant = variant;
								best_rw = v_rw;
								best_use_c = false;
								log("  cand %d (variant %d): fired=%d, committed by the "
								    "structural criterion (-no-probe; no synthesis paid)\n",
								    cand, variant, v_rw);
							}
							int kc2 = rewrite_sparse_arms(mx);
							if (kc2 >= 1) {
								if (best_variant == 0) {
									best_variant = 1;
									best_rw = kc2;
								} else {
									best_rw += kc2;
								}
								best_use_c = true;
								fired_seen = true;
								any_fired = true;
								log("  cand %d: stage C folds %d arm cell(s); +stageC rides "
								    "on the structural commit\n", cand, kc2);
							}
							break;
						}
							std::string dg;
							if (probe_it && !probe_all && !probed_digests.empty()) {
								dg = design_digest(d, top_name);
								if (std::find(probed_digests.begin(), probed_digests.end(), dg)
								    != probed_digests.end()) {


									gate_plans_pruned++;
									probe_it = false;
								}
							}
								if (probe_it) {
									if (!base_tried) {
										base_tried = true;
										gate_base_probes++;
										base_lut = probe_base_lut(design, top_name);
									}
									gate_plan_probes++;
									int probed = probe_luts_design(d, top_name);
									if (dg.empty())
										dg = design_digest(d, top_name);
									probed_digests.push_back(dg);


									log("  cand %d (variant %d%s): fired=%d, probe %d -> %d LUT\n",
									    cand, variant, (use_c ? " +C" : ""), v_rw,
									    base_lut, probed);
									if (probed >= 0 && v_rw >= 1 &&
									    (best_after < 0 || probed < best_after)) {
										best_after = probed;
										best_variant = variant;
										best_rw = v_rw;
										best_use_c = use_c;
									}
								}
						}
						delete d;
						d = nullptr;
					} catch (...) {
						delete d;
						d = nullptr;
					}
				}


				if (counter_enabled && best_variant > 0 && best_rw >= 1) {
					int d_after = -1, d_new = 0, d_rw = 0, d_pr = 0, d_sk = 0;
					RTLIL::Design *d = nullptr;
					try {
						if (no_probe && can_plan_module_locally(design, mod)) {
							d = new RTLIL::Design;
							d->add(mod->clone());
						} else {
							d = clone_design(design);
						}
						RTLIL::Module *mx = d->module(RTLIL::escape_id(top_name));
						if (mx) {


							if (!no_prio_or)
								rewrite_priority_or_chains(mx, d_new);
							rewrite_priority_cells(mx, d_new);
							probe_pre(d, best_variant);
							rewrite_stage_ab(mx, d_new, d_rw, d_pr, d_sk, 1, naive_enabled, 1);
							if (best_use_c)
								rewrite_sparse_arms(mx);


							if (best_use_fg) {
								rewrite_decode_share(mx, d_new);
								rewrite_sclr_promo(d, mx, d_new);
							}


							Pass::call(d, "check");
							gate_plan_probes++;
							d_after = probe_luts_design(d, top_name);
							log("  stage D probe: %d LUT (plan without D: %d)\n",
								    d_after, best_after);
						}
						delete d;
						d = nullptr;
					} catch (std::exception &exc) {
						log("  [dbg] stage D probe threw: %s\n", exc.what());
						d_after = -1;
						delete d;
						d = nullptr;
					} catch (...) {
						d_after = -1;
						delete d;
						d = nullptr;
					}

					if (d_after >= 0 && d_after < best_after) {
						best_after = d_after;
						best_use_d = true;
					}
				}


				int fg_after = -1, fg_new = 0, fg_rw = 0;
				bool fg_fires = false;


				bool mod_has_mem = false;
				for (Cell *c : mod->cells())
					if (c->type.in(ID($mem_v2), ID($memrd_v2), ID($memwr_v2), ID($meminit),
					               ID($mem), ID($memrd), ID($memwr), ID($meminit)))
						{ mod_has_mem = true; break; }
				bool fg_possible = !no_decode_share || !no_hold_extract ||
				                   (!no_sclr_promo && (!sclr_promo_rom_only || mod_has_mem));
				if (fg_allowed && fg_possible) {
					RTLIL::Design *d = nullptr;
					try {
						if (no_probe && can_plan_module_locally(design, mod)) {
							d = new RTLIL::Design;
							d->add(mod->clone());
						} else {
							d = clone_design(design);
						}
						RTLIL::Module *mx = d->module(RTLIL::escape_id(top_name));
						if (mx) {


							if (!no_prio_or)
								rewrite_priority_or_chains(mx, fg_new);
							rewrite_priority_cells(mx, fg_new);
							probe_pre(d, best_variant > 0 ? best_variant : 1);
							{
								int f2_new = 0, f2_rw = 0, f2_pr = 0, f2_sk = 0;
								rewrite_stage_ab(mx, f2_new, f2_rw, f2_pr, f2_sk, 1,
								                 naive_enabled, 1);
								fg_rw += f2_rw;
								fg_new += f2_new;
								probe_skipped += f2_sk;
							}
							if (best_use_c) {
								int n_c2 = rewrite_sparse_arms(mx);
								fg_rw += n_c2;
							}
							if (best_use_d) {
								int cn = 0;
								rewrite_next_state(mx, cn);
							}


							int k_h = no_hold_extract ? 0 : rewrite_hold_extract(mx, fg_new);
							int k_f = no_decode_share ? 0 : rewrite_decode_share(mx, fg_new);
							int k_g = no_sclr_promo ? 0 : rewrite_sclr_promo(d, mx, fg_new);
							fg_fires = (k_f + k_h + k_g) >= 1;
							fg_rw += k_f + k_h + k_g;
							if (fg_fires) {


								Pass::call(d, "check");
								if (no_probe) {


									if (best_variant == 0) {
										best_variant = 1;
										best_use_c = false;
										best_use_d = false;
									}
									best_use_fg = true;
									best_rw += fg_rw;
									log("  stage F/G: %d rewrite event(s) committed on the "
									    "structural criterion (-no-probe; no synthesis paid)\n",
									    fg_rw);
								} else {
									if (!base_tried) {
										base_tried = true;
										gate_base_probes++;
										base_lut = probe_base_lut(design, top_name);
									}
									gate_plan_probes++;
									fg_after = probe_luts_design(d, top_name);
									log("  stage F/G probe: %d LUT (phase-1 plan: %s%d)\n",
									    fg_after,
									    (best_variant > 0 ? "" : "unmodified "),
									    (best_variant > 0 ? best_after : base_lut));
								}
							}
						}
						delete d;
						d = nullptr;
					} catch (...) {
						delete d;
						d = nullptr;
						fg_after = -1;
						fg_fires = false;
					}
				}


				if (fg_fires && fg_after >= 0) {
					if (base_lut < 0) {
						base_tried = true;
						gate_base_probes++;
						base_lut = probe_base_lut(design, top_name);
					}
					bool beats_phase1 = (best_variant > 0) ? (fg_after < best_after)
					                                        : (fg_after < base_lut);
					if (base_lut >= 0 && fg_after < base_lut && beats_phase1) {
						if (best_variant == 0) {
							best_variant = 1;
							best_use_c = false;
							best_use_d = false;
						}
						best_after = fg_after;
						best_rw = fg_rw;
						best_use_fg = true;
					}
				}


				if (base_lut >= 0 && best_variant > 0 && best_after <= base_lut &&
				    best_rw >= 1) {
					plans.push_back({mod, best_variant, best_use_c, best_use_d, best_use_fg});
					log("  gate: committed %s (variant %d%s%s%s, probe %d -> %d LUT)\n",
						log_id(mod->name), best_variant,
						(best_use_c ? " +stageC" : ""), (best_use_d ? " +stageD" : ""),
						(best_use_fg ? " +FG" : ""),
						base_lut, best_after);
					} else if (base_lut < 0 && best_variant > 0 && best_rw >= 1) {


						if (no_probe)
							log("  gate: %s committed WITHOUT a benefit probe (-no-probe: structural "
							    "criterion only)\n", log_id(mod->name));


						plans.push_back({mod, 1, best_use_c, false, best_use_fg});
					log("  gate: committed %s (base probe unavailable; light plan%s)\n",
					    log_id(mod->name), (best_use_fg ? " +FG" : ""));
				} else {
					gate_skipped++;
					if (!fired_seen)


						log("  gate: %s has no firing PMUX rewrite candidate; "
						    "no synthesis paid for the gate\n", log_id(mod->name));
					else if (best_variant == 0)


						log("  gate: rolled back %s (no qualifying variant; base probe %d LUT)\n",
						    log_id(mod->name), base_lut);
					else
						log("  gate: rolled back %s (probe %d -> %d LUT, not smaller)\n",
						    log_id(mod->name), base_lut, best_after);
				}
			}


			for (Plan &pl : plans) {
				Module *mod = pl.mod;
				int t_new = 0;

				int k_e = no_prio_or ? 0 : rewrite_priority_or_chains(mod, t_new);
				if (k_e > 0) {
					prio_or_chains += k_e;
					rewritten += k_e;
					newcells += t_new;
				}
				int k = rewrite_priority_cells(mod, t_new);
				if (k > 0) {
					prio_cells += k;
					rewritten += k;
					newcells += t_new;
				}
				if (pl.variant == 2) {
					Pass::call_on_module(design, mod, "opt_muxtree");
					Pass::call_on_module(design, mod, "opt_merge -share_all");
					Pass::call_on_module(design, mod, "opt_clean");
					Pass::call_on_module(design, mod, "opt -nodffe -nosdff");
					Pass::call_on_module(design, mod, "opt");
					Pass::call_on_module(design, mod, "memory -nomap");
					Pass::call_on_module(design, mod, "opt_clean");
					Pass::call_on_module(design, mod, "opt -full");
					Pass::call_on_module(design, mod, "opt_clean");
				} else {
					Pass::call_on_module(design, mod, "opt_muxtree");
					Pass::call_on_module(design, mod, "opt_merge -share_all");
					Pass::call_on_module(design, mod, "opt_clean");
				}
				int c_new = 0, c_rw = 0, c_pr = 0, c_sk = 0;
				rewrite_stage_ab(mod, c_new, c_rw, c_pr, c_sk, 1,
				                 naive_enabled, 1);
				rewritten += c_rw;
				paired_cells += c_pr;
				skipped += c_sk;
				newcells += c_new;


				if (pl.use_fg) {


					int n_h = no_hold_extract ? 0 : rewrite_hold_extract(mod, newcells);
					hold_extracted += n_h;
					rewritten += n_h;
					int n_f = no_decode_share ? 0 : rewrite_decode_share(mod, newcells);
					decode_pairs += n_f;
					rewritten += n_f;
				}
				if (pl.use_c) {
					int n_c = rewrite_sparse_arms(mod);
					folded_cells += n_c;
					rewritten += n_c;
				}
				if (pl.use_d) {
					int cn = 0;
					int n_d = rewrite_next_state(mod, cn);
					ctr_cells += n_d;
					rewritten += n_d;
					newcells += cn;
				}
				if (pl.use_fg) {
					int n_g = no_sclr_promo ? 0 : rewrite_sclr_promo(design, mod, newcells);
					sclr_promoted += n_g;
					rewritten += n_g;
				}

			}


			if (preopt) {


				Pass::call(design, "opt");
				for (Module *mod : design->selected_modules()) {
					int t_new = 0;
					int k_e2 = no_prio_or ? 0 : rewrite_priority_or_chains(mod, t_new);
					if (k_e2 > 0) {
						prio_or_chains += k_e2;
						rewritten += k_e2;
						newcells += t_new;
					}
				}
			}
		}

		if (do_rewrite && general_mux_enabled) {
			for (Module *mod : design->selected_modules()) {
				int general_count = rewrite_general_mux(design, mod, newcells);
				general_transforms += general_count;
				rewritten += general_count;
				any_fired = any_fired || general_count > 0;
			}
		}


		for (Module *mod : design->selected_modules()) {
			for (Cell *cell : mod->cells()) {
				if (cell->type != ID($pmux) && cell->type != ID($mux))
					continue;
				total++;
				if (!cell->hasPort(ID(S)) || !cell->hasPort(ID(B)))
					continue;
				SigSpec s = cell->getPort(ID(S));
				SigSpec b = cell->getPort(ID(B));
				SigSpec a = cell->hasPort(ID(A)) ? cell->getPort(ID(A)) : SigSpec();
				int aw = GetSize(a), bw = GetSize(b), sw = GetSize(s);
				if (aw <= 0 || sw < 2 || bw != aw * sw)
					continue;
				int dup_pairs = 0;
				for (int i = 0; i < sw; i++) {
					for (int j = i + 1; j < sw; j++) {
						bool same = true;
						for (int k = 0; k < aw; k++) {
							SigBit bi = b[i * aw + k], bj = b[j * aw + k];
							if (bi.wire != bj.wire || bi.data != bj.data) {
								same = false;
								break;
							}
						}
						if (same) {
							dup_pairs++;
							break;
						}
					}
				}
				if (dup_pairs)
					multi++;
			}
		}


		log("PMUX_OPT_RTLIL: %d mux cells, %d with duplicate arms, "
			"%d rewritten (%d paired, %d priority, %d arm-folded, %d counter-compressed, "
			"%d prio-or, %d decode-shared, %d hold-extracted, %d pin-promoted, %d general-mux), "
		    "%d gate-skipped, %d commit-path rejection event(s), "
		    "%d probe-path rejection event(s), %d new cells.\n",
				total, multi, rewritten, paired_cells, prio_cells, folded_cells, ctr_cells,
		    prio_or_chains, decode_pairs, hold_extracted, sclr_promoted, general_transforms,
		    gate_skipped, skipped, probe_skipped, newcells);


		if (do_rewrite && total == 0)
			log("PMUX_OPT_RTLIL WARN: no $mux/$pmux cell is visible at this point -- the "
			    "structure was probably consumed by an earlier pass (already-mapped device "
			    "cells, or lowered to generic gates). Recommended position: right after "
			    "`proc`, before `synth_intel`; the measured position grid is in "
			    "results/flow_span/summary.json.\n");
		else if (do_rewrite && rewritten == 0 && any_fired)


			log("PMUX_OPT_RTLIL WARN: %d mux-like cell(s) scanned, a rewrite pattern DID "
			    "fire, but no variant came back strictly smaller -- output is unchanged by "
			    "the benefit gate, not by a missed pattern; see the `gate:` lines above.\n",
			    total);
		else if (do_rewrite && rewritten == 0)
			log("PMUX_OPT_RTLIL WARN: %d mux-like cell(s) scanned, none matched a rewrite "
			    "pattern -- output is unchanged by design, not by silence.\n", total);
		if (do_rewrite)
			log("PMUX_OPT_RTLIL benefit gate: %d whole-design synthesis(es) paid "
			    "(%d base + %d plan%s), %d candidate plan(s) skipped as "
			    "netlist-identical to one already paid for%s.\n",
			    gate_base_probes + gate_plan_probes, gate_base_probes,
			    gate_plan_probes, gate_plan_probes == 1 ? "" : "s",
			    gate_plans_pruned, probe_all ? " [-probe-all: exhaustive]" : "");
		log("Run `opt_clean` afterwards to drop the now-dead decoder cells.\n");
	}
} PmuxOptRtlilPass;
