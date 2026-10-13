using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

if(args.Length<2)throw new ArgumentException("CodeIndexer <code-files.jsonl> <output-directory> [platform]");
var platform=args.Length>2?args[2]:"UNITY_EDITOR";
Directory.CreateDirectory(args[1]);
var options=new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower};
var files=File.ReadLines(args[0]).Where(x=>!string.IsNullOrWhiteSpace(x)).Select(x=>JsonDocument.Parse(x).RootElement.Clone()).ToList();
using var nodesOut=new StreamWriter(Path.Combine(args[1],"code-nodes.jsonl"),false,new UTF8Encoding(false));
using var edgesOut=new StreamWriter(Path.Combine(args[1],"code-edges.jsonl"),false,new UTF8Encoding(false));
using var issuesOut=new StreamWriter(Path.Combine(args[1],"code-parse-issues.jsonl"),false,new UTF8Encoding(false));
string Val(JsonElement d,string k)=>d.TryGetProperty(k,out var v)?v.ToString():"";
string Hash(string text)=>Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();
string Key(params string[] a)=>Hash(string.Join("|",a));
void Emit(StreamWriter target,object v)=>target.WriteLine(JsonSerializer.Serialize(v,options));
var refs=((string?)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES")??"").Split(Path.PathSeparator).Where(File.Exists).Select(p=>MetadataReference.CreateFromFile(p)).ToList();
long nodeCount=0,edgeCount=0,unresolvedCount=0,parseErrors=0;
foreach(var group in files.GroupBy(d=>Val(d,"project"))){
 var trees=new List<SyntaxTree>();var meta=new Dictionary<SyntaxTree,JsonElement>();
 foreach(var d in group){
  var path=Val(d,"archive_path");var original=Val(d,"original_archive_path");var raw=File.ReadAllBytes(string.IsNullOrEmpty(original)?path:original);
  if(Convert.ToHexString(SHA256.HashData(raw)).ToLowerInvariant()!=Val(d,"source_hash"))throw new Exception("Source hash mismatch: "+path);
  var text=File.ReadAllText(path,Encoding.UTF8);
  var tree=CSharpSyntaxTree.ParseText(text,new CSharpParseOptions(LanguageVersion.Preview,preprocessorSymbols:new[]{platform,platform=="UNITY_EDITOR"?"UNITY_STANDALONE":"UNITY_MOBILE","UNITY_6000_2_OR_NEWER"}),Val(d,"source_path"));
  trees.Add(tree);meta[tree]=d;
  foreach(var e in tree.GetDiagnostics().Where(x=>x.Severity==DiagnosticSeverity.Error)){parseErrors++;Emit(issuesOut,new{project=group.Key,file=tree.FilePath,kind="syntax_error",diagnostic=e.Id,line=e.Location.GetLineSpan().StartLinePosition.Line+1});}
 }
 // Binding is limited to this source snapshot + .NET assemblies. Unity/external
 // unresolved symbols are retained as unresolved, never guessed by name.
 var compilation=CSharpCompilation.Create("AssetIndex_"+group.Key,trees,refs,new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary,allowUnsafe:true));
 var ids=new Dictionary<(SyntaxTree,int),string>();var candidates=new Dictionary<SyntaxTree,List<SyntaxNode>>();
 bool IsUnit(SyntaxNode n)=>n is BaseTypeDeclarationSyntax or DelegateDeclarationSyntax or BaseMethodDeclarationSyntax or PropertyDeclarationSyntax or IndexerDeclarationSyntax or FieldDeclarationSyntax or EventFieldDeclarationSyntax or EventDeclarationSyntax or AccessorDeclarationSyntax or LocalFunctionStatementSyntax;
 foreach(var tree in trees){
  var ns=tree.GetRoot().DescendantNodes().Where(IsUnit).ToList();candidates[tree]=ns;
  foreach(var n in ns)ids[(tree,n.SpanStart)]=Key(group.Key,tree.FilePath,Val(meta[tree],"source_hash"),n.Kind().ToString(),n.SpanStart.ToString());
 }
 string? TargetId(ISymbol? symbol){
  if(symbol==null)return null;
  foreach(var r in symbol.OriginalDefinition.DeclaringSyntaxReferences){var n=r.GetSyntax();while(n!=null){if(ids.TryGetValue((n.SyntaxTree,n.SpanStart),out var id))return id;n=n.Parent;}}
  return null;
 }
 foreach(var tree in trees){
  var d=meta[tree];var model=compilation.GetSemanticModel(tree,true);var root=tree.GetRoot();var source=tree.GetText();
  foreach(var n in candidates[tree]){
   var id=ids[(tree,n.SpanStart)];var parent=n.Ancestors().FirstOrDefault(x=>ids.ContainsKey((tree,x.SpanStart)));
   var parentId=parent==null?null:ids[(tree,parent.SpanStart)];
   ISymbol? symbol=null;try{symbol=model.GetDeclaredSymbol(n);}catch(ArgumentException){}
   string signature=symbol?.ToDisplayString(SymbolDisplayFormat.CSharpErrorMessageFormat)??n switch {
    FieldDeclarationSyntax f=>f.Declaration.ToString(),EventFieldDeclarationSyntax e=>e.Declaration.ToString(),_=>n.ChildTokens().Any()?string.Join(" ",n.ChildTokens().Select(t=>t.Text)):n.Kind().ToString()};
   var cls=n.AncestorsAndSelf().OfType<BaseTypeDeclarationSyntax>().FirstOrDefault()?.Identifier.Text??"";
   var namespaces=string.Join(".",n.Ancestors().OfType<BaseNamespaceDeclarationSyntax>().Reverse().Select(x=>x.Name.ToString()));
   var begin=n.SpanStart;var end=n.Span.End;var content=source.ToString(n.Span);
   var isContainer=n is BaseTypeDeclarationSyntax;
   var declaration=isContainer?string.Join(" ",n.ChildTokens().TakeWhile(t=>!t.IsKind(SyntaxKind.OpenBraceToken)).Select(t=>t.Text)):signature;
   // Full original spans are always preserved. Container vectors index declarations;
   // executable members index complete bodies or syntax-statement child blocks.
   var context=$"Project: {group.Key}\nGenre: {Val(d,"genre")}\nFeature (imported): {Val(d,"feature")}\nFile: {tree.FilePath}\nNamespace: {namespaces}\nClass: {cls}\nDeclaration: {declaration}\n";
   string input=isContainer?context+"Members:\n"+string.Join("\n",n.ChildNodes().OfType<MemberDeclarationSyntax>().Select(x=>x switch {BaseMethodDeclarationSyntax m=>m.ParameterList.ToString()+" "+string.Join(" ",m.ChildTokens().Select(t=>t.Text)),_=>x.Kind().ToString()})):context+content;
   bool longBody=input.Length>7000;
   if(longBody)input=context+"This member has syntax-block children; retrieve original span for the full implementation.";
   var span=tree.GetLineSpan(n.Span);
   Emit(nodesOut,new{id,project=group.Key,genre=Val(d,"genre"),classification_status="imported_unreviewed",feature=Val(d,"feature"),feature_evidence="legacy_metadata",source_path=tree.FilePath,source_hash=Val(d,"source_hash"),archive_path=Val(d,"archive_path"),source_file_id=Val(d,"id"),parent_id=parentId,namespace_name=namespaces,class_name=cls,symbol=signature,kind=n.Kind().ToString(),start=begin,length=end-begin,line_start=span.StartLinePosition.Line+1,line_end=span.EndLinePosition.Line+1,content,content_hash=Hash(content),embedding_text=input,representation=longBody?"declaration_with_block_children":isContainer?"container_declaration":"complete_member",status=tree.GetDiagnostics().Any(x=>x.Severity==DiagnosticSeverity.Error)?"syntax_errors_present":"parsed",binding_scope="source_and_dotnet; Unity/external symbols may be unresolved",runtime_verified=false});nodeCount++;
   if(parentId!=null){Emit(edgesOut,new{from=parentId,to=id,relation="contains",resolution="syntax",project=group.Key,file=tree.FilePath,line=span.StartLinePosition.Line+1});edgeCount++;}
   if(longBody && !isContainer){
    var parts=n.DescendantNodes().OfType<BlockSyntax>().FirstOrDefault()?.Statements.Cast<SyntaxNode>().ToList()??new List<SyntaxNode>();
    void Block(SyntaxNode part){
     var txt=source.ToString(part.Span);var text=context+txt;
     if(text.Length>7000 && part.ChildNodes().Any()){foreach(var child in part.ChildNodes())Block(child);return;}
     var bid=Key(id,"block",part.SpanStart.ToString(),part.Span.Length.ToString());var loc=tree.GetLineSpan(part.Span);
     Emit(nodesOut,new{id=bid,parent_id=id,project=group.Key,genre=Val(d,"genre"),feature=Val(d,"feature"),source_path=tree.FilePath,source_hash=Val(d,"source_hash"),archive_path=Val(d,"archive_path"),source_file_id=Val(d,"id"),class_name=cls,symbol=signature,kind="SyntaxBlock",start=part.SpanStart,length=part.Span.Length,line_start=loc.StartLinePosition.Line+1,line_end=loc.EndLinePosition.Line+1,content=txt,content_hash=Hash(txt),embedding_text=text.Length<=7000?text:null,status=text.Length<=7000?"parsed":"oversize_syntax_atom",runtime_verified=false});nodeCount++;
     Emit(edgesOut,new{from=id,to=bid,relation="contains_block",resolution="syntax",project=group.Key,file=tree.FilePath,line=loc.StartLinePosition.Line+1});edgeCount++;
    }
    foreach(var part in parts)Block(part);
    if(parts.Count==0)Emit(issuesOut,new{project=group.Key,file=tree.FilePath,kind="oversize_member_without_block",node_id=id});
   }
   // Only inspect operations owned by this unit, avoiding duplicated class-wide edges.
   foreach(var x in n.DescendantNodes().Where(x=>x is InvocationExpressionSyntax or ObjectCreationExpressionSyntax or AssignmentExpressionSyntax or BaseTypeSyntax or IdentifierNameSyntax or MemberAccessExpressionSyntax)){
    var owner=x.Ancestors().FirstOrDefault(IsUnit);if(owner!=n)continue;
    if(x is IdentifierNameSyntax && x.Parent is MemberAccessExpressionSyntax ma && ma.Name==x)continue;
    ISymbol? target=null;try{target=model.GetSymbolInfo(x is BaseTypeSyntax bt?bt.Type:x is AssignmentExpressionSyntax ae?ae.Left:x).Symbol;}catch(ArgumentException){}
    if(x is IdentifierNameSyntax or MemberAccessExpressionSyntax){
     if(target is not (IFieldSymbol or IPropertySymbol or IEventSymbol or INamedTypeSymbol))continue;
    }
    var targetId=TargetId(target);string relation=x switch {InvocationExpressionSyntax=>"calls",ObjectCreationExpressionSyntax=>"constructs",BaseTypeSyntax=>"inherits_or_implements",AssignmentExpressionSyntax ae when ae.IsKind(SyntaxKind.AddAssignmentExpression)&&target is IEventSymbol=>"subscribes",AssignmentExpressionSyntax ae when ae.IsKind(SyntaxKind.SubtractAssignmentExpression)&&target is IEventSymbol=>"unsubscribes",_=>"writes"};
    if(x is IdentifierNameSyntax or MemberAccessExpressionSyntax)relation=target is INamedTypeSymbol?"references_type":"references_member";
    var resolution=targetId!=null?"semantic_source":target!=null?"semantic_external":"unresolved";
    if(resolution=="unresolved")unresolvedCount++;
    Emit(edgesOut,new{from=id,to=targetId,relation,resolution,target_symbol=target?.ToDisplayString(SymbolDisplayFormat.CSharpErrorMessageFormat),expression=x.ToString(),project=group.Key,file=tree.FilePath,line=tree.GetLineSpan(x.Span).StartLinePosition.Line+1,source_hash=Val(d,"source_hash")});edgeCount++;
   }
  }
  foreach(var trivia in root.DescendantTrivia(descendIntoTrivia:true).Where(t=>t.IsKind(SyntaxKind.DisabledTextTrivia))){
   Emit(issuesOut,new{project=group.Key,file=tree.FilePath,kind="conditional_branch_not_bound",start=trivia.SpanStart,length=trivia.Span.Length,source_hash=Val(d,"source_hash")});
  }
 }
 nodesOut.Flush();edgesOut.Flush();issuesOut.Flush();Console.WriteLine($"{group.Key}: {group.Count()} files; total nodes={nodeCount} edges={edgeCount}");
}
File.WriteAllText(Path.Combine(args[1],"code-index-summary.json"),JsonSerializer.Serialize(new{source_files=files.Count,nodes=nodeCount,edges=edgeCount,unresolved_edges=unresolvedCount,syntax_errors=parseErrors,parser="Roslyn SDK 10",semantics="source snapshot + .NET; no Unity build performed",generated_at=DateTimeOffset.UtcNow},options));
