// Scripted tag editing through the Halo 3 Editing Kit's ManagedBlam.
//
//   mbedit.exe <H3EK folder> <script file>
//
// The script is one command per line, fields separated by tabs:
//   load    <tag path> <extension>
//   new     <tag path> <extension>
//   saveas  <tag path> <extension>
//   save
//   dump    <field path> [depth]
//   count   <block path>
//   add     <block path>              (prints the new element's index)
//   remove  <block path> <index>
//   clear   <block path>
//   set     <field path> <value>
//   copyfrom <src tag> <src ext> <src field path> <dst field path> [skip,field,names]
//                                     (copies a struct/block/field from another tag, name by name)
//   bspdump <structure bsp tag> <output file>   (collision bsps for h3kit.collision.load_collision)
// A field path is field names joined by '/', with [i] after a block's name to
// pick an element; a struct is entered by its name. References take
// "path,extension"; enums take an index or item name; arrays take
// comma-separated values. Lines starting with # are skipped.
using System;
using System.IO;
using System.Linq;
using Bungie;
using Bungie.Tags;

class MbEdit
{
    static TagFile tag;

    static int Main(string[] args)
    {
        ManagedBlamSystem.InitializeProject(InitializationType.TagsOnly, args[0]);
        int line = 0;
        try
        {
            foreach (var raw in File.ReadAllLines(args[1]))
            {
                line++;
                if (raw.Trim().Length == 0 || raw.StartsWith("#")) continue;
                Run(raw.Split('\t'));
            }
        }
        catch (Exception e)
        {
            Console.Error.WriteLine("line " + line + ": " + e.Message);
            return 1;
        }
        finally
        {
            if (tag != null) tag.Dispose();
        }
        return 0;
    }

    static void Run(string[] c)
    {
        switch (c[0])
        {
            case "load":
                if (tag != null) tag.Dispose();
                tag = new TagFile(TagPath.FromPathAndExtension(c[1], c[2]));
                break;
            case "new":
                if (tag != null) tag.Dispose();
                tag = new TagFile();
                tag.New(TagPath.FromPathAndExtension(c[1], c[2]));
                break;
            case "saveas":
                tag.SaveAs(TagPath.FromPathAndExtension(c[1], c[2]));
                break;
            case "save":
                tag.Save();
                break;
            case "dump":
                Dump(c[1].Length == 0 ? tag.Fields : new[] { Find(c[1]) }, "", c.Length > 2 ? int.Parse(c[2]) : 2);
                break;
            case "count":
                Console.WriteLine(((TagFieldBlock)Find(c[1])).Elements.Count);
                break;
            case "add":
                var block = (TagFieldBlock)Find(c[1]);
                block.AddElement();
                Console.WriteLine(block.Elements.Count - 1);
                break;
            case "remove":
                ((TagFieldBlock)Find(c[1])).RemoveElement(int.Parse(c[2]));
                break;
            case "clear":
                ((TagFieldBlock)Find(c[1])).RemoveAllElements();
                break;
            case "set":
                Set(Find(c[1]), c.Length > 2 ? c[2] : "", c[1]);
                break;
            case "bspdump":
                BspDump(c[1], c[2]);
                break;
            case "copyfrom":
                // copyfrom <src tag> <src ext> <src field path> <dst field path> [skip,names]
                using (var src = new TagFile(TagPath.FromPathAndExtension(c[1], c[2])))
                {
                    var skip = c.Length > 5 ? c[5].Split(',') : new string[0];
                    Copy(FindIn(src.Fields, c[3]), Find(c[4]), skip);
                }
                break;
            default:
                throw new Exception("unknown command " + c[0]);
        }
    }

    static TagField Find(string path)
    {
        return FindIn(tag.Fields, path);
    }

    // copy a field's value, or a struct's / block's / array's contents, name by name
    static void Copy(TagField s, TagField d, string[] skip)
    {
        if (s is TagFieldStruct && d is TagFieldStruct)
            CopyFields(((TagFieldStruct)s).Elements[0].Fields, ((TagFieldStruct)d).Elements[0].Fields, skip);
        else if (s is TagFieldBlock && d is TagFieldBlock)
        {
            var sb = (TagFieldBlock)s; var db = (TagFieldBlock)d;
            db.RemoveAllElements();
            for (int i = 0; i < sb.Elements.Count; i++)
            {
                db.AddElement();
                CopyFields(sb.Elements[i].Fields, db.Elements[i].Fields, skip);
            }
        }
        else if (s is TagFieldArray && d is TagFieldArray)
        {
            var sa = (TagFieldArray)s; var da = (TagFieldArray)d;
            for (int i = 0; i < Math.Min(sa.Elements.Count, da.Elements.Count); i++)
                CopyFields(sa.Elements[i].Fields, da.Elements[i].Fields, skip);
        }
        else if (s is TagFieldReference && d is TagFieldReference) ((TagFieldReference)d).Path = ((TagFieldReference)s).Path;
        else if (s is TagFieldEnum && d is TagFieldEnum) ((TagFieldEnum)d).Value = ((TagFieldEnum)s).Value;
        else if (s is TagFieldFlags && d is TagFieldFlags) ((TagFieldFlags)d).RawValue = ((TagFieldFlags)s).RawValue;
        else if (s is TagFieldBlockIndex && d is TagFieldBlockIndex) ((TagFieldBlockIndex)d).Value = ((TagFieldBlockIndex)s).Value;
        else if (s is TagFieldBlockFlags && d is TagFieldBlockFlags) ((TagFieldBlockFlags)d).Value = ((TagFieldBlockFlags)s).Value;
        else if (s is TagFieldData && d is TagFieldData) ((TagFieldData)d).SetData(((TagFieldData)s).GetData());
        else if (s is TagFieldElementArray && d is TagFieldElementArray)
            ((TagFieldElementArray)d).SetStringData(((TagFieldElementArray)s).GetStringData());
        else if (s is TagFieldElement && d is TagFieldElement)
        {
            var p = s.GetType().GetProperty("Data"); var q = d.GetType().GetProperty("Data");
            if (p != null && q != null && q.CanWrite && p.PropertyType == q.PropertyType) q.SetValue(d, p.GetValue(s, null), null);
            else ((TagFieldElement)d).SetStringData(((TagFieldElement)s).GetStringData());
        }
    }

    static void CopyFields(TagField[] src, TagField[] dst, string[] skip)
    {
        foreach (var s in src)
        {
            if (string.IsNullOrEmpty(s.FieldName) || skip.Any(n => string.Equals(n, s.FieldName, StringComparison.OrdinalIgnoreCase))) continue;
            if (s is TagFieldCustom || s is TagFieldExplanation) continue;
            var d = dst.FirstOrDefault(f => f.FieldName == s.FieldName && f.GetType() == s.GetType());
            if (d != null) Copy(s, d, skip);
        }
    }

    static TagField FindIn(TagField[] fields, string path)
    {
        TagField found = null;
        foreach (var part in path.Split('/'))
        {
            string name = part;
            int index = -1;
            int open = part.LastIndexOf('[');
            if (open > 0 && part.EndsWith("]"))
            {
                name = part.Substring(0, open);
                index = int.Parse(part.Substring(open + 1, part.Length - open - 2));
            }
            if (fields == null) throw new Exception("'" + part + "' is past a plain field in " + path);
            // a struct can share its name with an editor-only field (a function's
            // custom editor, an explanation); take the struct
            found = fields.Where(f => string.Equals(f.FieldName, name, StringComparison.OrdinalIgnoreCase))
                          .OrderBy(f => f is TagFieldStruct || f is TagFieldBlock || f is TagFieldArray ? 0 :
                                        f is TagFieldCustom || f is TagFieldExplanation ? 2 : 1).FirstOrDefault();
            if (found == null)
                throw new Exception("no field '" + name + "' in " + path + "; there are: " +
                                    string.Join(", ", fields.Select(f => f.FieldName)));
            fields = null;
            if (found is TagFieldBlock)
            {
                var b = (TagFieldBlock)found;
                if (index >= 0)
                {
                    if (index >= b.Elements.Count) throw new Exception(path + ": element " + index + " of " + b.Elements.Count);
                    fields = b.Elements[index].Fields;
                }
            }
            else if (found is TagFieldStruct)
            {
                fields = ((TagFieldStruct)found).Elements[0].Fields;
            }
            else if (found is TagFieldArray)
            {
                if (index >= 0) fields = ((TagFieldArray)found).Elements[index].Fields;
            }
        }
        return found;
    }

    static void Set(TagField f, string value, string path)
    {
        if (f is TagFieldReference)
        {
            var r = (TagFieldReference)f;
            if (value.Length == 0) { r.Path = null; return; }
            int comma = value.LastIndexOf(',');
            r.Path = TagPath.FromPathAndExtension(value.Substring(0, comma), value.Substring(comma + 1));
        }
        else if (f is TagFieldEnum)
        {
            var e = (TagFieldEnum)f;
            int v;
            if (int.TryParse(value, out v)) e.Value = v;
            else
            {
                var item = e.Items.FirstOrDefault(i => string.Equals(i.EnumName, value, StringComparison.OrdinalIgnoreCase));
                if (item == null) throw new Exception(path + ": no item '" + value + "'; there are: " + string.Join(", ", e.Items.Select(i => i.EnumName)));
                e.Value = item.EnumIndex;
            }
        }
        else if (f is TagFieldFlags) ((TagFieldFlags)f).RawValue = Convert.ToUInt32(value, value.StartsWith("0x") ? 16 : 10);
        else if (f is TagFieldBlockIndex) ((TagFieldBlockIndex)f).Value = int.Parse(value);
        else if (f is TagFieldBlockFlags) ((TagFieldBlockFlags)f).Value = Convert.ToUInt32(value, value.StartsWith("0x") ? 16 : 10);
        else if (f is TagFieldData) ((TagFieldData)f).SetData(Convert.FromBase64String(value));  // base64, as export-tag-to-xml prints it
        else if (f is TagFieldElementArray)
        {
            if (!((TagFieldElementArray)f).SetStringData(value.Split(',')))
                throw new Exception(path + ": cannot set '" + value + "'");
        }
        else if (f is TagFieldElement)
        {
            if (!((TagFieldElement)f).SetStringData(value))
                throw new Exception(path + ": cannot set '" + value + "'");
        }
        else throw new Exception(path + ": cannot set a " + f.GetType().Name);
    }

    // bspdump <structure bsp tag path> <output file>: the structure's collision bsp
    // and every instanced geometry definition's (3d nodes as int64, planes), plus
    // the instances, for h3kit.collision.load_collision(). Does not touch the open tag.
    static void BspDump(string bspPath, string outFile)
    {
        using (var t = new TagFile(TagPath.FromPathAndExtension(bspPath, "scenario_structure_bsp")))
        {
            var o = new System.Text.StringBuilder();
            var inst = (TagFieldBlock)Field(t.Fields, "instanced geometry instances");
            o.AppendLine("instances " + inst.Elements.Count);
            foreach (var e in inst.Elements)
                o.AppendLine(string.Join("|", e.Fields.Where(f => !(f is TagFieldBlock) && !(f is TagFieldStruct))
                                                    .Select(f => f.FieldName + "=" + Plain(f))));
            var raw = ((TagFieldStruct)Field(t.Fields, "resource interface")).Elements[0].Fields;
            var items = ((TagFieldStruct)Field(((TagFieldBlock)Field(raw, "raw_resources")).Elements[0].Fields,
                                               "raw_items")).Elements[0].Fields;
            o.AppendLine("structure");
            CollisionBsp(((TagFieldBlock)Field(items, "collision bsp")).Elements[0].Fields, o);
            var defs = (TagFieldBlock)Field(items, "instanced geometries definitions");
            o.AppendLine("defs " + defs.Elements.Count);
            foreach (var e in defs.Elements)
            {
                o.AppendLine("def");
                CollisionBsp(((TagFieldStruct)Field(e.Fields, "collision info")).Elements[0].Fields, o);
            }
            File.WriteAllText(outFile, o.ToString());
        }
    }

    static TagField Field(TagField[] fields, string name)
    {
        var f = fields.FirstOrDefault(x => string.Equals(x.FieldName, name, StringComparison.OrdinalIgnoreCase));
        if (f == null) throw new Exception("no field '" + name + "'; there are: " + string.Join(", ", fields.Select(x => x.FieldName)));
        return f;
    }

    static void CollisionBsp(TagField[] c, System.Text.StringBuilder o)
    {
        var nodes = (TagFieldBlock)Field(c, "bsp3d nodes");
        o.AppendLine("nodes " + nodes.Elements.Count);
        foreach (var e in nodes.Elements) o.AppendLine(Plain(e.Fields[0]));
        var planes = (TagFieldBlock)Field(c, "planes");
        o.AppendLine("planes " + planes.Elements.Count);
        foreach (var e in planes.Elements) o.AppendLine(Plain(e.Fields[0]));
    }

    // a plain field's value; integer elements (int64 included, which GetStringData leaves blank) via Data
    static string Plain(TagField f)
    {
        var p = f.GetType().GetProperty("Data");
        if (p != null)
        {
            var v = p.GetValue(f, null);
            if (v is Array) return string.Join(",", ((Array)v).Cast<object>().Select(x => Convert.ToString(x, System.Globalization.CultureInfo.InvariantCulture)));
            return Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture);
        }
        if (f is TagFieldElementArray) return string.Join(",", ((TagFieldElementArray)f).GetStringData());
        if (f is TagFieldBlockIndex) return ((TagFieldBlockIndex)f).Value.ToString();
        if (f is TagFieldFlags) return ((TagFieldFlags)f).RawValue.ToString();
        if (f is TagFieldEnum) return ((TagFieldEnum)f).Value.ToString();
        if (f is TagFieldElement) return ((TagFieldElement)f).GetStringData();
        return "";
    }

    static void Dump(TagField[] fields, string indent, int depth)
    {
        foreach (var f in fields)
        {
            string head = indent + f.FieldName + " [" + f.GetType().Name.Replace("TagField", "") + "]";
            if (f is TagFieldBlock)
            {
                var b = (TagFieldBlock)f;
                Console.WriteLine(head + " count=" + b.Elements.Count);
                if (depth > 0)
                    for (int i = 0; i < Math.Min(b.Elements.Count, 2); i++)
                    {
                        Console.WriteLine(indent + "  [" + i + "]");
                        Dump(b.Elements[i].Fields, indent + "    ", depth - 1);
                    }
            }
            else if (f is TagFieldStruct)
            {
                Console.WriteLine(head);
                Dump(((TagFieldStruct)f).Elements[0].Fields, indent + "  ", depth);
            }
            else if (f is TagFieldArray)
            {
                var a = (TagFieldArray)f;
                Console.WriteLine(head + " count=" + a.Elements.Count);
                if (depth > 0 && a.Elements.Count > 0) Dump(a.Elements[0].Fields, indent + "    ", depth - 1);
            }
            else if (f is TagFieldReference) Console.WriteLine(head + " = " + ((TagFieldReference)f).Path);
            else if (f is TagFieldEnum)
            {
                var e = (TagFieldEnum)f;
                var item = e.Items.FirstOrDefault(i => i.EnumIndex == e.Value);
                Console.WriteLine(head + " = " + e.Value + (item != null ? " (" + item.EnumName + ")" : ""));
            }
            else if (f is TagFieldFlags) Console.WriteLine(head + " = 0x" + ((TagFieldFlags)f).RawValue.ToString("x") + " [" + string.Join(", ", ((TagFieldFlags)f).Items.Select(i => i.FlagName)) + "]");
            else if (f is TagFieldBlockIndex) Console.WriteLine(head + " = " + ((TagFieldBlockIndex)f).Value);
            else if (f is TagFieldData) Console.WriteLine(head + " = " + Convert.ToBase64String(((TagFieldData)f).GetData()));
            else if (f is TagFieldElementArray) Console.WriteLine(head + " = " + string.Join(", ", ((TagFieldElementArray)f).GetStringData()));
            else if (f is TagFieldElement) Console.WriteLine(head + " = " + ((TagFieldElement)f).GetStringData());
            else Console.WriteLine(head);
        }
    }
}
