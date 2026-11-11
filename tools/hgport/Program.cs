// hgport: moves tags, with everything they depend on, from one Halo 3 MCC map
// into another, using Assembly's Blamite library (vendor/Blamite) and plugins
// (vendor/Plugins). It does what Assembly's GUI does for "Extract" then
// "Import": the extraction follows the HaloMap.xaml.cs extractTags() path and
// the injection uses the GUI's default settings.
//
//   hgport info    <map>
//   hgport list    <map> <group>
//   hgport extract <src.map> <out.tagc> <shared maps dir> [--existing <dst.map>] <group:tag path>...
//                  --existing: a tag the destination already has (same group
//                  and name) goes in as a name only, without its data or what
//                  it references, since the injection would reuse it anyway;
//                  except shader-pipeline tags (SHADER_GROUPS), which the
//                  injection copies under unique names (see Inject)
//   hgport inject  <dst.map> <in.tagc>
//   hgport rename  <map> <group:tag path> <new path>
//   hgport fsb     <in.tagc>                  (FMOD bank suffixes the sounds use)
//   hgport compare <a.tagc> <b.tagc> [names]  (tag-by-tag: data, references by
//                  name, string ids by text, resources by content; names is a
//                  file of "group:path" lines to restrict the report to)
//
// Run with the exe's folder as the working directory: Formats\ and Plugins\
// are found relative to it.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml;
using Blamite.Blam;
using Blamite.Blam.Resources;
using Blamite.Blam.Resources.Sounds;
using Blamite.Blam.ThirdGen;
using Blamite.Injection;
using Blamite.IO;
using Blamite.Plugins;
using Blamite.Serialization;
using Blamite.Serialization.Settings;
using Blamite.Util;

static class Program
{
	static EngineDatabase _db;
	// compiled shader templates, shaders and their definitions: a map's own copies are
	// compiled for it, so an injected shader brings its own (renamed "<name>_0x<datum>")
	static readonly HashSet<string> SHADER_GROUPS = new HashSet<string> { "pixl", "vtsh", "rmt2", "rmdf", "glps", "glvs", "mtsb", "mats" };

	static int Main(string[] args)
	{
		if (args.Length < 2)
		{
			Console.Error.WriteLine("usage: hgport info|list|extract|inject|fsb ...");
			return 2;
		}
		_db = XMLEngineDatabaseLoader.LoadDatabase("Formats/Engines.xml");
		try
		{
			switch (args[0])
			{
				case "info": return Info(args[1]);
				case "list": return List(args[1], args[2]);
				case "extract": return Extract(args[1], args[2], args[3], args.Skip(4).ToArray());
				case "inject": return Inject(args[1], args[2]);
				case "rename": return Rename(args[1], args[2], args[3]);
				case "fsb": return Fsb(args[1]);
				case "compare": return Compare(args[1], args[2], args.Length > 3 ? args[3] : null);
			}
		}
		catch (Exception ex)
		{
			Console.Error.WriteLine("hgport: " + ex);
			return 1;
		}
		Console.Error.WriteLine("hgport: unknown command " + args[0]);
		return 2;
	}

	static ICacheFile Open(Stream stream, string path, out EngineDescription info)
	{
		var reader = new EndianReader(stream, Endian.BigEndian);
		var matches = CacheFileLoader.FindEngineDescriptions(reader, _db);
		if (matches.Count == 0)
			throw new NotSupportedException(path + ": no matching engine in Formats/Engines.xml");
		info = matches[0];
		return CacheFileLoader.LoadCacheFileWithEngineDescription(reader, path, info);
	}

	static string Name(ICacheFile cache, ITag tag)
	{
		return cache.FileNames.GetTagName(tag) ?? tag.Index.ToString();
	}

	static int Info(string path)
	{
		using (var fs = File.OpenRead(path))
		{
			var cache = Open(fs, path, out var info);
			Console.WriteLine("engine\t" + info.Name);
			Console.WriteLine("internal\t" + cache.InternalName);
			Console.WriteLine("tags\t" + cache.Tags.Count);
			Console.WriteLine("optimized shaders\t" + info.OptimizedShaders);
			Console.WriteLine("raw hashes\t" + info.UsesRawHashes);
			Console.WriteLine("sound gestalt\t" + (cache.SoundGestalt != null));
		}
		return 0;
	}

	static int List(string path, string group)
	{
		using (var fs = File.OpenRead(path))
		{
			var cache = Open(fs, path, out _);
			int magic = CharConstant.FromString(group);
			foreach (var t in cache.Tags)
				if (t != null && t.Group != null && t.Group.Magic == magic)
					Console.WriteLine(Name(cache, t));
		}
		return 0;
	}

	static string PluginPath(EngineDescription info, int magic)
	{
		string group = Regex.Replace(CharConstant.ToString(magic), @"(\.+$)|([<>:""/\\|?*])", "_").Trim();
		string path = Path.Combine("Plugins", info.Settings.GetSetting<string>("plugins"), group + ".xml");
		if (!File.Exists(path) && info.Settings.PathExists("fallbackPlugins"))
			path = Path.Combine("Plugins", info.Settings.GetSetting<string>("fallbackPlugins"), group + ".xml");
		return File.Exists(path) ? path : null;
	}

	static HashSet<string> TagKeys(string path)
	{
		var keys = new HashSet<string>();
		using (var fs = File.OpenRead(path))
		{
			var cache = Open(fs, path, out _);
			foreach (var t in cache.Tags)
				if (t != null && t.Group != null)
					keys.Add(CharConstant.ToString(t.Group.Magic) + ":" + Name(cache, t));
		}
		return keys;
	}

	static int Rename(string path, string tagKey, string newName)
	{
		using (var fs = File.Open(path, FileMode.Open, FileAccess.ReadWrite))
		{
			var cache = Open(fs, path, out _);
			int colon = tagKey.IndexOf(':');
			var tag = cache.Tags.FindTagByName(tagKey.Substring(colon + 1), tagKey.Substring(0, colon), cache.FileNames);
			if (tag == null)
				throw new ArgumentException("no tag " + tagKey + " in " + path);
			if (cache.Tags.FindTagByName(newName, tagKey.Substring(0, colon), cache.FileNames) != null)
				throw new ArgumentException(path + " already has " + newName);
			cache.FileNames.SetTagName(tag, newName);
			cache.SaveChanges(new EndianStream(fs, cache.Endianness));
			Console.WriteLine("renamed	{0}	{1}	0x{2:x8}", tagKey, newName, tag.Index.Value);
		}
		return 0;
	}

	static int Extract(string src, string outPath, string sharedDir, string[] args)
	{
		HashSet<string> existing = null;
		var roots = new List<string>();
		for (int i = 0; i < args.Length; i++)
		{
			if (args[i] == "--existing")
				existing = TagKeys(args[++i]);
			else
				roots.Add(args[i]);
		}
		var stubs = new HashSet<ITag>();
		var container = new TagContainer();
		var tagsToProcess = new Queue<ITag>();
		var tagsProcessed = new HashSet<ITag>();
		var resourcesToProcess = new Queue<DatumIndex>();
		var resourcesProcessed = new HashSet<DatumIndex>();
		var pagesProcessed = new HashSet<ResourcePage>();
		var codecs = new Queue<int>(); var pitchRanges = new Queue<int>(); var langDurations = new Queue<int>();
		var playbacks = new Queue<int>(); var scales = new Queue<int>(); var promotions = new Queue<int>();
		var customPlaybacks = new Queue<int>(); var extraInfos = new Queue<int>();
		var missingPlugins = new SortedSet<string>();

		using (var fs = File.OpenRead(src))
		{
			var cache = Open(fs, src, out var info);
			var reader = new EndianReader(fs, cache.Endianness);
			foreach (var root in roots)
			{
				int colon = root.IndexOf(':');
				var tag = cache.Tags.FindTagByName(root.Substring(colon + 1), root.Substring(0, colon), cache.FileNames);
				if (tag == null)
					throw new ArgumentException("no tag " + root + " in " + src);
				tagsToProcess.Enqueue(tag);
			}

			ResourceTable resources = null;
			SoundResourceTable soundResources = null;
			while (tagsToProcess.Count > 0)
			{
				var current = tagsToProcess.Dequeue();
				if (tagsProcessed.Contains(current))
					continue;
				if (existing != null && !SHADER_GROUPS.Contains(CharConstant.ToString(current.Group.Magic))
					&& existing.Contains(CharConstant.ToString(current.Group.Magic) + ":" + Name(cache, current)))
				{
					uint stubAddress = cache.PointerExpander.Contract(current.MetaLocation.AsPointer());
					container.AddTag(new ExtractedTag(current.Index, stubAddress, current.Group.Magic, Name(cache, current)));
					tagsProcessed.Add(current);
					stubs.Add(current);
					continue;
				}
				string plugin = PluginPath(info, current.Group.Magic);
				if (plugin == null)
				{
					missingPlugins.Add(CharConstant.ToString(current.Group.Magic));
					tagsProcessed.Add(current);
					continue;
				}
				var builder = new DataBlockBuilder(reader, current, cache, info);
				using (var pr = XmlReader.Create(plugin))
					AssemblyPluginLoader.LoadPlugin(pr, builder);
				foreach (var block in builder.DataBlocks)
					container.AddDataBlock(block);
				uint cont = cache.PointerExpander.Contract(current.MetaLocation.AsPointer());
				container.AddTag(new ExtractedTag(current.Index, cont, current.Group.Magic, Name(cache, current)));
				tagsProcessed.Add(current);

				foreach (var r in builder.ReferencedTags)
					tagsToProcess.Enqueue(cache.Tags[r]);
				foreach (var r in builder.ReferencedResources)
					resourcesToProcess.Enqueue(r);
				if (builder.ContainsSoundReferences && soundResources == null && cache.SoundGestalt != null)
					soundResources = cache.SoundGestalt.LoadSoundResourceTable(reader);
				foreach (var i in builder.ReferencedSoundCodecs) codecs.Enqueue(i);
				foreach (var i in builder.ReferencedSoundPitchRanges) pitchRanges.Enqueue(i);
				foreach (var i in builder.ReferencedSoundLanguagePitchRanges) langDurations.Enqueue(i);
				foreach (var i in builder.ReferencedSoundPlaybacks) playbacks.Enqueue(i);
				foreach (var i in builder.ReferencedSoundScales) scales.Enqueue(i);
				foreach (var i in builder.ReferencedSoundPromotions) promotions.Enqueue(i);
				foreach (var i in builder.ReferencedSoundCustomPlaybacks)
				{
					customPlaybacks.Enqueue(i);
					if (soundResources != null)
					{
						var cpb = soundResources.CustomPlaybacks[i];
						if (cpb.RadioEffect != null)
							tagsToProcess.Enqueue(cache.Tags[cpb.RadioEffect.Index]);
						if (cpb.Components != null)
							foreach (var comp in cpb.Components)
								if (comp.Sound != null)
									tagsToProcess.Enqueue(cache.Tags[comp.Sound.Index]);
					}
				}
				foreach (var i in builder.ReferencedSoundExtraInfo) extraInfos.Enqueue(i);
			}
			if (resourcesToProcess.Count > 0 && cache.Resources != null)
				resources = cache.Resources.LoadResourceTable(reader);

			if (soundResources != null)
			{
				foreach (var i in codecs.Distinct())
					container.AddSoundCodec(new ExtractedSoundCodec(i, soundResources.Codecs[i]));
				foreach (var i in pitchRanges.Distinct())
				{
					var pRange = soundResources.PitchRanges[i];
					var perms = new List<ExtractedSoundPermutation>();
					foreach (var p in pRange.Permutations)
					{
						var exP = new ExtractedSoundPermutation
						{
							Name = cache.StringIDs.GetString(p.Name),
							EncodedSkipFraction = p.EncodedSkipFraction,
							EncodedGain = p.EncodedGain,
							EncodedPermutationInfoIndex = p.EncodedPermutationInfoIndex,
							SampleSize = p.SampleSize,
							FSBInfo = p.FSBInfo,
							Chunks = new List<ExtractedSoundChunk>(),
						};
						foreach (var chunk in p.Chunks)
							exP.Chunks.Add(new ExtractedSoundChunk(chunk, cache.StringIDs.GetString(chunk.FModBankSuffix)));
						if (p.Languages != null)
						{
							exP.Languages = new List<ExtractedSoundLanguagePermutation>();
							foreach (var lang in p.Languages)
							{
								var exLP = new ExtractedSoundLanguagePermutation
								{
									LanguageIndex = lang.LanguageIndex,
									SampleSize = lang.SampleSize,
									Chunks = new List<ExtractedSoundChunk>(),
								};
								foreach (var chunk in p.Chunks)
									exLP.Chunks.Add(new ExtractedSoundChunk(chunk, cache.StringIDs.GetString(chunk.FModBankSuffix)));
								exP.Languages.Add(exLP);
							}
						}
						if (p.LayerMarkers != null)
							exP.LayerMarkers = new List<int>(p.LayerMarkers);
						perms.Add(exP);
					}
					container.AddSoundPitchRange(new ExtractedSoundPitchRange(i, cache.StringIDs.GetString(pRange.Name), pRange, perms));
				}
				foreach (var i in langDurations.Distinct())
				{
					var exLD = new ExtractedSoundLanguageDuration(i);
					foreach (var lang in soundResources.LanguageDurations)
					{
						var exLI = new ExtractedSoundLanguageDurationInfo { LanguageIndex = lang.LanguageIndex, Durations = new List<int>() };
						exLI.Durations.AddRange(lang.PitchRanges[i].Durations);
						exLD.Languages.Add(exLI);
					}
					container.AddSoundLanguageDuration(exLD);
				}
				foreach (var i in playbacks.Distinct())
					container.AddSoundPlayback(new ExtractedSoundPlayback(i, soundResources.Playbacks[i]));
				foreach (var i in scales.Distinct())
					container.AddSoundScale(new ExtractedSoundScale(i, soundResources.Scales[i]));
				foreach (var i in promotions.Distinct())
					container.AddSoundPromotion(new ExtractedSoundPromotion(i, soundResources.Promotions[i]));
				foreach (var i in customPlaybacks.Distinct())
					container.AddSoundCustomPlayback(new ExtractedSoundCustomPlayback(i, soundResources.CustomPlaybacks[i]));
				foreach (var i in extraInfos.Distinct())
				{
					container.AddSoundExtraInfo(new ExtractedSoundExtraInfo(i, soundResources.ExtraInfos[i]));
					if (soundResources.ExtraInfos[i].Datums != null)
						foreach (var datum in soundResources.ExtraInfos[i].Datums)
							if (datum != DatumIndex.Null)
								resourcesToProcess.Enqueue(datum);
				}
			}

			if (resources != null)
			{
				while (resourcesToProcess.Count > 0)
				{
					var index = resourcesToProcess.Dequeue();
					if (!resourcesProcessed.Add(index))
						continue;
					var resource = resources.Resources[index.Index];
					container.AddResource(new ExtractedResourceInfo(index, resource));
					if (resource.Location == null)
						continue;
					foreach (ResourcePage page in resource.Location.PagesToArray())
					{
						if (page == null || !pagesProcessed.Add(page))
							continue;
						container.AddResourcePage(page);
						ICacheFile pageCache = cache;
						Stream pageStream = fs;
						FileStream external = null;
						if (page.FilePath != null)
						{
							string ext = Path.Combine(sharedDir, Path.GetFileName(page.FilePath));
							if (!File.Exists(ext))
								throw new FileNotFoundException("resource cache " + ext + " is missing");
							external = File.OpenRead(ext);
							pageStream = external;
							pageCache = new ThirdGenCacheFile(new EndianReader(external, cache.Endianness), info, ext);
						}
						using (var ms = new MemoryStream())
						{
							new ResourcePageExtractor(pageCache).ExtractPage(page, pageStream, ms);
							container.AddExtractedResourcePage(new ExtractedPage(ms.ToArray(), page.Index));
						}
						external?.Dispose();
					}
				}

				foreach (ITag t in tagsProcessed.Where(t => !stubs.Contains(t)))
				{
					foreach (var pred in resources.Predictions.Where(d => d.Tag.Index == t.Index))
					{
						var expred = new ExtractedResourcePredictionMolecule(pred);
						foreach (var pc in pred.MoleculeAtoms)
						{
							var expc = new ExtractedResourcePredictionMoleculeAtom(pc);
							foreach (var pa in pc.Atom.Quantas)
								expc.BEntry.Quantas.Add(Quanta(cache, resources, pa));
							expred.MoleculeAtoms.Add(expc);
						}
						foreach (var pa in pred.Quantas)
							expred.Quantas.Add(Quanta(cache, resources, pa));
						container.AddPrediction(expred);
					}
				}
			}
		}

		using (var writer = new EndianWriter(File.Open(outPath, FileMode.Create, FileAccess.Write), Endian.LittleEndian))
			TagContainerWriter.WriteTagContainer(container, writer);
		Console.WriteLine("existing\t{0} tags referenced by name only", stubs.Count);
		Console.WriteLine("extracted\t{0} tags, {1} blocks, {2} pages, {3} raw pages, {4} resources, {5} predictions",
			container.Tags.Count, container.DataBlocks.Count, container.ResourcePages.Count,
			container.ExtractedResourcePages.Count, container.Resources.Count, container.Predictions.Count);
		foreach (var g in missingPlugins)
			Console.WriteLine("no plugin\t" + g);
		foreach (var g in container.Tags.GroupBy(t => CharConstant.ToString(t.Group)).OrderBy(g => g.Key))
			Console.WriteLine("group\t{0}\t{1}", g.Key, g.Count());
		return missingPlugins.Count == 0 ? 0 : 3;
	}

	static ExtractedResourcePredictionQuanta Quanta(ICacheFile cache, ResourceTable resources, ResourcePredictionQuanta pa)
	{
		var expa = new ExtractedResourcePredictionQuanta(pa);
		var res = resources.Resources[pa.Resource.Index];
		if (res.ParentTag != null)
		{
			expa.OriginalResourceName = cache.FileNames.GetTagName(res.ParentTag);
			expa.OriginalResourceGroup = res.ParentTag.Group.Magic;
		}
		else
		{
			expa.OriginalResourceName = "null";
			expa.OriginalResourceGroup = -1;
		}
		return expa;
	}

	static int Inject(string dst, string tagc)
	{
		TagContainer container;
		using (var reader = new EndianReader(File.OpenRead(tagc), Endian.LittleEndian))
			container = TagContainerReader.ReadTagContainer(reader);
		using (var fs = File.Open(dst, FileMode.Open, FileAccess.ReadWrite))
		{
			var cache = Open(fs, dst, out var info);
			var stream = new EndianStream(fs, cache.Endianness);
			// The GUI's defaults (keep sounds, inject raw pages, look for existing pages
			// only where the engine hashes them, add the resource predictions), except
			// unique shader names always: a shader reusing the target's same-named
			// template, compiled for the target, drew white.
			var injector = new TagContainerInjector(cache, container, info, true, true, info.UsesRawHashes, true);
			int existing = container.Tags.Count(t => cache.Tags.FindTagByName(t.Name, t.Group, cache.FileNames) != null);
			foreach (ExtractedTag tag in container.Tags)
				injector.InjectTag(tag, stream);
			injector.InjectPredictions(container.Predictions, stream);
			injector.SaveChanges(stream);
			Console.WriteLine("injected\t{0} tags ({1} already present), {2} blocks, {3} pages, {4} raw pages, {5} resources, {6} string ids",
				injector.InjectedTags.Count, existing, injector.InjectedBlocks.Count, injector.InjectedPages.Count,
				injector.InjectedExtractedResourcePages.Count, injector.InjectedResources.Count, injector.InjectedStringIDs.Count);
		}
		return 0;
	}

	static TagContainer ReadContainer(string path)
	{
		using (var reader = new EndianReader(File.OpenRead(path), Endian.LittleEndian))
			return TagContainerReader.ReadTagContainer(reader);
	}

	static string TagKey(ExtractedTag t)
	{
		return t == null ? "null" : CharConstant.ToString(t.Group) + ":" + t.Name;
	}

	static int Compare(string pathA, string pathB, string namesFile)
	{
		var a = ReadContainer(pathA);
		var b = ReadContainer(pathB);
		var only = namesFile == null ? null : new HashSet<string>(File.ReadAllLines(namesFile).Select(l => l.Trim()).Where(l => l.Length > 0));
		var byKey = new Dictionary<string, ExtractedTag>();
		foreach (var t in b.Tags)
			byKey[TagKey(t)] = t;
		int same = 0, differ = 0, missing = 0;
		// a renamed copy in the destination ("<name>_<index>") stands for its original
		var copyOf = new Dictionary<string, string>();
		foreach (var k in (IEnumerable<string>)only ?? byKey.Keys)
		{
			int us = k.LastIndexOf('_');
			if (us > 0 && UniqueCopy(k.Substring(0, us), k))
				copyOf[k.Substring(0, us)] = k;
		}
		foreach (var ta in a.Tags.OrderBy(TagKey))
		{
			string key = TagKey(ta);
			string bkey = only == null || only.Contains(key) ? key : (copyOf.TryGetValue(key, out var c) ? c : null);
			if (bkey == null)
				continue;
			if (!byKey.TryGetValue(bkey, out var tb))
			{
				missing++;
				Console.WriteLine("missing\t" + key);
				continue;
			}
			string why = CompareBlock(a, a.FindDataBlock(ta.OriginalAddress), b, b.FindDataBlock(tb.OriginalAddress), "", new HashSet<DataBlock>());
			if (why == null)
				same++;
			else
			{
				differ++;
				Console.WriteLine("differs\t" + key + "\t" + why);
			}
		}
		Console.WriteLine("compare\t{0} identical, {1} differ, {2} missing", same, differ, missing);
		return differ + missing == 0 ? 0 : 4;
	}

	static string CompareBlock(TagContainer ca, DataBlock a, TagContainer cb, DataBlock b, string path, HashSet<DataBlock> seen)
	{
		if (a == null || b == null)
			return a == b ? null : path + ": block missing";
		if (!seen.Add(a))
			return null;
		if (a.Data.Length != b.Data.Length || a.EntryCount != b.EntryCount)
			return string.Format("{0}: size {1}x{2} vs {3}x{4}", path, a.EntryCount, a.Data.Length, b.EntryCount, b.Data.Length);
		// a sortable block (sort="true") is re-sorted by string id value on injection,
		// where the ids change: match its entries by their first string id instead
		int size = a.EntryCount > 0 ? a.Data.Length / a.EntryCount : 0;
		var perm = Enumerable.Range(0, a.EntryCount).ToArray();
		if (a.Sortable && a.EntryCount > 1)
		{
			string Label(DataBlock blk, int e) =>
				blk.StringIDFixups.FirstOrDefault(f => f.WriteOffset == e * size)?.OriginalString;
			var where = new Dictionary<string, int>();
			for (int e = 0; e < b.EntryCount; e++)
			{
				string l = Label(b, e);
				if (l != null) where[l] = e;
			}
			for (int e = 0; e < a.EntryCount; e++)
			{
				string l = Label(a, e);
				if (l == null || !where.TryGetValue(l, out perm[e]))
					return string.Format("{0}: sorted entry {1} ({2}) not found", path, e, l);
			}
		}
		int Map(int o) => size == 0 ? o : perm[o / size] * size + o % size;
		var mask = new HashSet<int>();
		void Mask(int offset, int length) { for (int i = 0; i < length; i++) mask.Add(offset + i); }
		foreach (var f in a.AddressFixups) Mask(f.WriteOffset, 4);
		foreach (var f in a.TagFixups) Mask(f.WriteOffset, 4);
		foreach (var f in a.ResourceFixups) Mask(f.WriteOffset, 4);
		foreach (var f in a.StringIDFixups) Mask(f.WriteOffset, 4);
		foreach (var f in a.InteropFixups) Mask(f.WriteOffset, 4);
		foreach (var f in a.EffectFixups) Mask(f.WriteOffset, 4);
		foreach (var f in a.UnicListFixups) Mask(f.WriteOffset, 4);
		foreach (var f in a.ShaderFixups) Mask(f.WriteOffset, 4);
		// a sound's gestalt indices are rewritten on injection and carry no
		// write offset, so a block with sound fixups isn't byte-compared
		if (a.SoundFixups.Count == 0)
			for (int i = 0; i < a.Data.Length; i++)
				if (!mask.Contains(i) && a.Data[i] != b.Data[Map(i)])
				return string.Format("{0}: byte 0x{1:x} of {2}", path, i, a.Data.Length);

		var tagsB = b.TagFixups.ToDictionary(f => f.WriteOffset);
		foreach (var f in a.TagFixups)
		{
			if (!tagsB.TryGetValue(Map(f.WriteOffset), out var g))
				return string.Format("{0}: tag ref at 0x{1:x} missing", path, f.WriteOffset);
			string na = f.OriginalIndex == DatumIndex.Null ? "null" : TagKey(ca.FindTag(f.OriginalIndex));
			string nb = g.OriginalIndex == DatumIndex.Null ? "null" : TagKey(cb.FindTag(g.OriginalIndex));
			if (na != nb && !UniqueCopy(na, nb))
				return string.Format("{0}: tag ref at 0x{1:x}: {2} vs {3}", path, f.WriteOffset, na, nb);
		}
		var stringsB = b.StringIDFixups.ToDictionary(f => f.WriteOffset);
		foreach (var f in a.StringIDFixups)
			if (!stringsB.TryGetValue(Map(f.WriteOffset), out var g) || g.OriginalString != f.OriginalString)
				return string.Format("{0}: string id at 0x{1:x}: {2} vs {3}", path, f.WriteOffset, f.OriginalString, g?.OriginalString);
		var resB = b.ResourceFixups.ToDictionary(f => f.WriteOffset);
		foreach (var f in a.ResourceFixups)
		{
			if (!resB.TryGetValue(Map(f.WriteOffset), out var g))
				return string.Format("{0}: resource at 0x{1:x} missing", path, f.WriteOffset);
			string why = CompareResource(ca, f.OriginalIndex, cb, g.OriginalIndex);
			if (why != null)
				return string.Format("{0}: resource at 0x{1:x}: {2}", path, f.WriteOffset, why);
		}
		var shadersB = b.ShaderFixups.ToDictionary(f => f.WriteOffset);
		foreach (var f in a.ShaderFixups)
			if (!shadersB.TryGetValue(Map(f.WriteOffset), out var g) || !Same(f.Data, g.Data))
				return string.Format("{0}: shader at 0x{1:x}", path, f.WriteOffset);
		var effectsB = b.EffectFixups.ToDictionary(f => f.WriteOffset);
		foreach (var f in a.EffectFixups)
			if (!effectsB.TryGetValue(Map(f.WriteOffset), out var g) || f.Type != g.Type || !Same(f.Data, g.Data))
				return string.Format("{0}: effect data at 0x{1:x}", path, f.WriteOffset);
		if (a.SoundFixups.Count != b.SoundFixups.Count)
			return path + ": sound fixups";
		var addrB = b.AddressFixups.ToDictionary(f => f.WriteOffset);
		foreach (var f in a.AddressFixups.OrderBy(f => f.WriteOffset))
		{
			if (!addrB.TryGetValue(Map(f.WriteOffset), out var g))
				return string.Format("{0}: pointer at 0x{1:x} missing", path, f.WriteOffset);
			string why = CompareBlock(ca, ca.FindDataBlock(f.OriginalAddress), cb, cb.FindDataBlock(g.OriginalAddress),
				string.Format("{0}/0x{1:x}", path, f.WriteOffset), seen);
			if (why != null)
				return why;
		}
		return null;
	}

	// "<group>:<name>_0x<datum>": the injection's unique copy of a shader-pipeline tag
	// (TagContainerInjector appends the original tag's datum index)
	static bool UniqueCopy(string original, string copy)
	{
		return SHADER_GROUPS.Contains(original.Split(':')[0]) && copy.StartsWith(original + "_")
			&& Regex.IsMatch(copy.Substring(original.Length + 1), "^(0x[0-9A-Fa-f]+|[0-9]+)$");
	}

	static string CompareResource(TagContainer ca, DatumIndex ia, TagContainer cb, DatumIndex ib)
	{
		if (ia == DatumIndex.Null || ib == DatumIndex.Null)
			return (ia == DatumIndex.Null) == (ib == DatumIndex.Null) ? null : "null vs set";
		var ra = ca.FindResource(ia);
		var rb = cb.FindResource(ib);
		if (ra == null || rb == null)
			return ra == rb ? null : "not extracted";
		if (ra.Type != rb.Type || ra.Flags != rb.Flags)
			return "type " + ra.Type + " vs " + rb.Type;
		if (!Same(ra.Info, rb.Info))
			return "definition data";
		if ((ra.Location == null) != (rb.Location == null))
			return "location";
		if (ra.Location == null)
			return null;
		var la = ra.Location;
		var lb = rb.Location;
		if (la.PrimaryOffset != lb.PrimaryOffset || la.SecondaryOffset != lb.SecondaryOffset || la.TertiaryOffset != lb.TertiaryOffset)
			return "page offsets";
		foreach (var pair in new[] { (la.OriginalPrimaryPageIndex, lb.OriginalPrimaryPageIndex), (la.OriginalSecondaryPageIndex, lb.OriginalSecondaryPageIndex), (la.OriginalTertiaryPageIndex, lb.OriginalTertiaryPageIndex) })
		{
			if ((pair.Item1 < 0) != (pair.Item2 < 0))
				return "page presence";
			if (pair.Item1 < 0)
				continue;
			var pa = ca.FindExtractedResourcePage(pair.Item1);
			var pb = cb.FindExtractedResourcePage(pair.Item2);
			if (pa == null || pb == null)
				return "page not extracted";
			if (!Same(pa.ExtractedPageData, pb.ExtractedPageData))
				return "page bytes";
		}
		return null;
	}

	static bool Same(byte[] x, byte[] y)
	{
		if (x == null || y == null)
			return x == y;
		return x.Length == y.Length && x.SequenceEqual(y);
	}

	static int Fsb(string tagc)
	{
		var container = ReadContainer(tagc);
		var names = new SortedSet<string>();
		foreach (var pr in container.SoundPitchRanges)
			foreach (var p in pr.Permutations)
			{
				foreach (var c in p.Chunks)
					names.Add(c.FModBankSuffix);
				if (p.Languages != null)
					foreach (var l in p.Languages)
						foreach (var c in l.Chunks)
							names.Add(c.FModBankSuffix);
			}
		Console.Error.WriteLine("{0} sound tags, {1} pitch ranges, {2} permutations, {3} chunks",
			container.Tags.Count(t => CharConstant.ToString(t.Group) == "snd!"), container.SoundPitchRanges.Count,
			container.SoundPitchRanges.Sum(pr => pr.Permutations.Count),
			container.SoundPitchRanges.Sum(pr => pr.Permutations.Sum(p => p.Chunks.Count)));
		foreach (var n in names)
			Console.WriteLine(n);
		return 0;
	}
}
