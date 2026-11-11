# Print a tag's field tree (names, types, values) via ManagedBlam.
#   dump_tag.ps1 <tag path without extension> <group extension> [field path] [max elements per block] [H3EK folder]
param([string]$TagPath, [string]$Extension, [string]$FieldPath = "", [int]$MaxElements = 2,
      [string]$ek = "C:\Program Files (x86)\Steam\steamapps\common\H3EK")
$ErrorActionPreference = "Stop"
Add-Type -Path "$ek\bin\ManagedBlam.dll"
$params = New-Object Bungie.ManagedBlamStartupParameters
$params.InitializationLevel = [Bungie.InitializationType]::TagsOnly
[Bungie.ManagedBlamSystem]::Start($ek, $null, $params)
try {
  $tag = New-Object Bungie.Tags.TagFile
  $tag.Load([Bungie.Tags.TagPath]::FromPathAndExtension($TagPath, $Extension))
  function Show($fields, $indent, $depth) {
    foreach ($f in $fields) {
      $t = $f.GetType().Name
      $line = "$indent$($f.FieldName) [$t]"
      if ($f -is [Bungie.Tags.TagFieldBlock]) {
        "$line count=$($f.Elements.Count)"
        if ($depth -lt 4) { $i = 0; foreach ($e in $f.Elements) { if ($i -ge $MaxElements) { break }; "$indent  [$i]"; Show $e.Fields "$indent    " ($depth + 1); $i++ } }
      } elseif ($f -is [Bungie.Tags.TagFieldStruct]) {
        $line; foreach ($e in $f.Elements) { Show $e.Fields "$indent  " ($depth + 1) }
      } elseif ($f -is [Bungie.Tags.TagFieldReference]) { "$line = $($f.Path)" }
      elseif ($f -is [Bungie.Tags.TagFieldElement]) { "$line = $($f.GetStringData())" }
      elseif ($f -is [Bungie.Tags.TagFieldElementArray]) { "$line = $(($f.GetStringData()) -join ', ')" }
      elseif ($f -is [Bungie.Tags.TagFieldEnum]) { "$line = $($f.Value) ($(($f.Items | ? { $_.EnumIndex -eq $f.Value } | % { $_.EnumName }) -join ''))" }
      elseif ($f -is [Bungie.Tags.TagFieldFlags]) { "$line = 0x$('{0:x}' -f $f.RawValue)" }
      elseif ($f -is [Bungie.Tags.TagFieldBlockIndex]) { "$line = $($f.Value)" }
      else { $line }
    }
  }
  if ($FieldPath) { $root = @($tag.SelectField($FieldPath)) } else { $root = $tag.Fields }
  Show $root "" 0
  $tag.Dispose()
} finally { [Bungie.ManagedBlamSystem]::Stop() }
