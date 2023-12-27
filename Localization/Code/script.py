
#
# Imports
# 

import os
from pprint import pprint
import git
import re
import subprocess
import tempfile

#
# Constants
#

# Get info
repo_root = os.getcwd()

#
# Main
#

def main():

    # Log
    print(f'Finding translation files inside MMF repo...')

    # Find localization files in MMF repo
    files = find_localization_files_in_mmf_repo(repo_root)
    
    # Analyze localization files
    
    # Log
    print(f'Analyzing localization files...')
    
    # Get 'outdating commits'
    #   This is a more primitive method than analyzing the changes to translation keys. Should only be relevant for files that don't have translation keys
    
    print(f'  Analyzing outdating commits...')
    git_repo = git.Repo(repo_root)
    for file_dict in files:
        base_file = file_dict['base']
        
        for translation_file, translation_dict in file_dict['translations'].items():
            
            
            translation_commit_iterator = git_repo.iter_commits(paths=translation_file, **{'max-count': 1} ) # max-count is passed along to `git rev-list` command-line-arg
            last_translation_commit = next(translation_commit_iterator)
            
            outdating_commits = []
            
            base_commit_iterator = git_repo.iter_commits(paths=base_file)
            
            for base_commit in base_commit_iterator:
                if not is_predecessor(base_commit, last_translation_commit):
                    outdating_commits.append(base_commit)
                else:
                    break
            
                
            if len(outdating_commits) > 0:
                translation_dict['outdating_commits'] = outdating_commits
    
    
    # Log
    print(f'  Analyzing changes to translation keys...')
    
    # Analyze changes to translation keys
    for file_dict in files:
        
        # Get base file info
        base_file_path = file_dict['base']
        _, file_type = os.path.splitext(base_file_path)
        
        # Skip
        if not (file_type == '.js' or file_type == '.strings' or file_type == '.xib' or file_type == '.storyboard'):
            continue
        
        # Log
        print(f'    Processing base translation at {base_file_path}...')
        
        # Find basefile keys
        base_keys_and_values = extract_translation_keys_and_values_from_file(file_dict['base'])
        if base_keys_and_values == None: continue
        base_keys = set(base_keys_and_values.keys())
        
        # For each key in the base file, get the commit, when it last changed  
        latest_base_changes = get_latest_change_for_translation_keys(base_keys, base_file_path, git_repo)
        
        for translation_file_path, translation_dict in file_dict['translations'].items():
            
            # Log
            print(f'      Processing translation of {os.path.basename(base_file_path)} at {translation_file_path}...')
            print(f'        Find translation keys and values...')
            
            # Find translation file keys
            translation_keys_and_values = extract_translation_keys_and_values_from_file(translation_file_path)
            translation_keys = set(translation_keys_and_values.keys())
            
            print(f'        Check missing/superfluous keys...')
            
            # Do set operations
            missing_keys = base_keys.difference(translation_keys)
            superfluous_keys = translation_keys.difference(base_keys)
            common_keys = base_keys.intersection(translation_keys)
            
            # Attach set operation data
            translation_dict['missing_keys'] = missing_keys
            translation_dict['superfluous_keys'] = superfluous_keys
            
            # Log
            print(f'        Analyze when keys last changed...')
            
            # Check common keys if they are outdated.
            
            # For each key, get the commit when it last changed
            latest_translation_changes = get_latest_change_for_translation_keys(common_keys, translation_file_path, git_repo)
            
            # Log
            print(f'        Check if last modification was before base for each key ...')
            
            # Compare time of latest change for each key between base file and translation file
            for k in common_keys:
                
                # if k == 'capture-toast.body':
                #     pprint(f"translation_dict: {translation_dict}")
                #     break
                
                base_commit = latest_base_changes[k]
                translation_commit = latest_translation_changes[k]
                
                base_commit_is_predecessor = is_predecessor(base_commit, translation_commit)
                
                # DEBUG
                # if file_dict['basetype'] == 'IB':
                #     print(f"latest_base_change: {base_file_path}, change: {base_commit}")
                #     print(f"translated_change: {translation_file_path}, change: {translation_commit}")
                #     print(f"base_is_predecessor: {base_commit_is_predecessor}")
                
                if not base_commit_is_predecessor:
                    translation_dict.setdefault('outdated_keys', {})[k] = { 'latest_base_change': base_commit, 'latest_translation_change': translation_commit }    
    
    pprint(files)
        

#
# Change analysis
#

def get_latest_change_for_translation_keys(wanted_keys, file_path, git_repo):
    
    # Declare stuff
    result = dict()
    wanted_keys = wanted_keys.copy()
    _, file_type = os.path.splitext(file_path)
    
    # Preprocess file_type
    t = 'strings' if (file_type == '.strings' or file_type == '.js') else 'IB' if (file_type == '.xib' or file_type == '.storyboard') else None
    if t == None:
        assert False, f"Trying to get latest key changes for incompatible filetype {file_type}"
    
    
    if t == 'strings':
        
        for i, commit in enumerate(git_repo.iter_commits(paths=file_path, reverse=False)):
            
            # Break
            if len(wanted_keys) == 0:
                break
            
            # Get diff string
            #   Run git command 
            #   - For getting additions and deletions of the commit compared to its parent
            #   - I tried to do this with gitpython but nothing worked, maybe I should stop using it altogether?
            diff_string = runCLT(f"git diff -U0 {commit.hexsha}^..{commit.hexsha} -- {file_path}").stdout
            
            # Parse translation key/value diffs
            # Note: This should be the exact same between the 'strings' and the 'IB' code. Keep it in sync!
            
            keys_and_values = extract_translation_keys_and_values_from_string(diff_string)
        
            for key, changes in keys_and_values.items():
                
                if (key not in result) and (key in wanted_keys):
                    if changes.get('added', None) != changes.get('deleted', None):
                        result[key] = commit
                        wanted_keys.remove(key)    
                
    elif t == 'IB':
        
        commits = list(git_repo.iter_commits(paths=file_path, reverse=False))
        commits.append(None)
        
        last_strings_file_path = ''
        
        for i, commit in enumerate(commits):
            
            # Break
            if len(wanted_keys) == 0:
                break
            
            # Get strings file for this commit
            if commit == None:
                # This case is weird
                #   The 'None' commit symbolizes the parent of the initial commit of the file.
                #   We say the parent of the strings file at the initial commit is an empty file, that way we can get meaningful diff values for the initial commit.
                assert i == (len(commits) - 1)
                strings_file_path = create_temp_file()
            else:
                file_path_relative = os.path.relpath(file_path, repo_root) # `git show` breaks with absolute paths
                file_path_at_this_commit = create_temp_file(suffix=file_type)
                runCLT(f"git show {commit.hexsha}:{file_path_relative} > {file_path_at_this_commit}")
                # print(f"Extracting from: {file_path_at_this_commit}. Base: {commit.hexsha}:{file_path} Content: {read_tempfile(file_path_at_this_commit, remove=False)}")
                strings_file_path = extract_strings_from_IB_file_to_temp_file(file_path_at_this_commit)
                
            if i != 0: 
                
                # Notes: 
                #  We skip the first iteration. That's because, on the first iteration,
                #  there's no `last_strings_file_path` to diff against.
                #  To 'make up' for this lack of diff on the first iteration, we have the extra 'None' commit. 
                #  Kind of confusing but it should work.
                
                # Get diff string
                diff_string = runCLT(f"git diff -U0 --no-index -- {last_strings_file_path} {strings_file_path}").stdout
                
                # Parse translation key/value diffs
                # Note: This should be the exact same between the 'strings' and the 'IB' code. Keep it in sync!
                
                keys_and_values = extract_translation_keys_and_values_from_string(diff_string)
            
                for key, changes in keys_and_values.items():
                    
                    if (key not in result) and (key in wanted_keys):
                        if changes.get('added', None) != changes.get('deleted', None):
                            result[key] = commits[i-1]
                            wanted_keys.remove(key)    

                # Cleanup
                os.remove(last_strings_file_path)
            
            # Update state
            last_strings_file_path = strings_file_path
            
            
    else:
        assert False
            

        
    # Return
    
    return result

#
# File-level analysis
#

def extract_translation_keys_and_values_from_file(file_path):
    
    # Read file content
    text = ''
    with open(file_path, 'r') as file:
        text = file.read()

    # Get extension
    _, file_type = os.path.splitext(file_path)
    
    if file_type == '.xib' or file_type == '.storyboard':
        
        # Extract strings from IB file    
        temp_file_path = extract_strings_from_IB_file_to_temp_file(file_path)
        strings_text = read_tempfile(temp_file_path)

        # Call
        result = extract_translation_keys_and_values_from_string(strings_text)
    else: 
        result = extract_translation_keys_and_values_from_string(text)
    
    # Return
    return result
    
#
# Core string-level analysis
#
    
def extract_translation_keys_and_values_from_string(text):

    """
    Extract translation keys and values from text. Should work on Xcode .strings files and nuxt i18n .js files.
    Structure of result:
    {
        <translation_key>: {
            added<?>: <translation_value>,
            deleted<?>: <translation_value>,
            value<?>: <translation_value>,
        }
        <translation_key>: {
            ...
        },
        ... 
    }

    ... where <?> means that the key is optional. 
        If the input text is a git diff text with - and + at the start of lines, then the result with contain `added` and `deleted` keys, otherwise, the result will contain `value` keys.
    """
        
    # Strings file regex:
    #   Used to get keys and values from strings files. Designed to work on Xcode .strings files and on the .js strings files used on the MMF website. (Won't work on `.stringsdict`` files, those are xml)
    #   See https://regex101.com
    strings_file_regex = re.compile(r'^(\+?\-?)\s*[\'\"]([^\'\"]+)[\'\"]\s*[=:]\s*[\'\"]([^\'\"]*)[\'\"]', re.MULTILINE)
    
    # Find matches
    matches = strings_file_regex.finditer(text)
    
    # Parse matches
    
    result = dict()
    for match in matches:
        git_line_diff = match.group(1)
        translation_key = match.group(2)
        translation_value = match.group(3)
        
        k = 'added' if git_line_diff == '+' else 'deleted' if git_line_diff == '-' else 'value'
        result.setdefault(translation_key, {})[k] = translation_value
        
        # if translation_key == 'capture-toast.body':
            # print(f"{git_line_diff} value: {translation_value} isNone: {translation_value is None}") # /Users/Noah/Desktop/mmf-stuff/mac-mouse-fix/Localization/de.lproj/Localizable.strings
            # print(f"result: {result}")
            
    return result

    # else:
    #     assert False, f"translation key/value finder encountered unparsable file type: {file_type}"
    
    # elif file_type == '.xib' or file_type == '.storyboard':
        
        # Trying to analyze the IB files directly didn't work, because they are too complex. Instead, we'll parse them to .strings files and then analyze those.
        
        # # Validate
        # assert wanted_keys != None
            
        # # Extract values for the wanted_keys
        # #   We're doing this weird regex stuff to implement this. Not sure if it's a good solution. See regex101.com to understand the regexes.
    
        # regex1_template = r'^([\+\-]?)\s*<[^>]*{attribute}="([^"]*)"[^>]*id="{object_id}"'
        # regex2_template  = r'^([\+\-]?)\s*<[^>]*id="{object_id}"[^>]*{attribute}="([^"]*)"' # Template2 covers the case that the object_id comes before the attribute_name (not sure this ever happens)
        
        # result = dict()
        
        # for translation_key in wanted_keys:
            
        #     # Get object_id and attribute_name from the `.strings` file key
        #     object_id, ui_attribute = translation_key.split('.', 1)
            
        #     # Compile regexes
        #     #   Not sure what re.MULTILINE does. We copied that from the regex for parsing strings-files
        #     regex1 = re.compile(regex1_template.format(object_id=object_id, attribute=ui_attribute), re.MULTILINE)
        #     regex2 = re.compile(regex2_template.format(object_id=object_id, attribute=ui_attribute), re.MULTILINE)
            
        #     # Find match
        #     #   Not sure why were using findall() here and finditer() in the .strings implementation
        #     matches = regex1.findall(text)
        #     if len(matches) == 0:
        #         matches = regex2.findall(text)

        #     # Validate
        #     assert len(matches) <= 2
            
        #     for match in matches:
                
        #         # Extract group values from match (groups are the parts inside (parenthesis) in the regex_template)
        #         git_line_diff = match[0]
        #         translation_value = match[1]
                
        #         # Store in dict
        #         k = 'added' if git_line_diff == '+' else 'deleted' if git_line_diff == '-' else 'value'
        #         assert k != 'value'
        #         result.setdefault(translation_key, {})[k] = translation_value
            
            
        # DEBUG
        # print(f"Diff for IB: {result}")
            
        # Return
        # return result 
    
    # elif file_type == '.stringsdict':
    #     return None
    # elif file_type == '.md':
    #     return None
    # else:
    #     assert False, f"translation key/value finder encountered unknown file type: {file_type}"

#
# Analysis helpers
#

def create_temp_file(suffix=''):
    
    # Returns temp_file_path
    #   Use os.remove(temp_file_path) after you're done with it
    
    temp_file_path = ''
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file_path = temp_file.name
    return temp_file_path

def extract_strings_from_IB_file_to_temp_file(ib_file_path):
    
    temp_file_path = create_temp_file()
        
    cltResult = subprocess.run(f"/usr/bin/ibtool --export-strings-file {temp_file_path} {ib_file_path}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
    if len(cltResult.stdout) > 0 or len(cltResult.stderr) > 0:
        # print(f"Error: ibtool failed. Printing feedback ... \nstdout: {cltResult.stdout}\nstderr: {cltResult.stderr}")
        exit(1)
    
    # Convert to utf-8
    #   For some reason, ibtool outputs strings files as utf-16, even though strings files in Xcode are utf-8 and also git doesn't understand utf-8.
    convert_utf16_file_to_utf8(temp_file_path)
    
    return temp_file_path

def read_tempfile(temp_file_path, remove=True):
    
    result = ''
    
    with open(temp_file_path, 'r', encoding='utf-8') as temp_file:
        result = temp_file.read()
    
    if remove:
        os.remove(temp_file_path)
    
    return result

def convert_utf16_file_to_utf8(file_path):
    
    content = ''
    
    # Read from UTF-16 file
    with open(file_path, 'r', encoding='utf-16') as file:
        content = file.read()

    # Write back to the same file in UTF-8
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

def is_predecessor(potential_predecessor_commit, commit):
    
    # Check which commit is 'earlier'. Works kind of like potential_predecessor_commit <= commit (returns true for equality)
    # Not totally sure what we're doing here. 
    #   - First, we were checking for ancestry with `git merge-base``, but that slowed the whole script down a lot (maybe we could've alleviated that by changing runCLT? We have some weird options there.) (We also tried `rev-list --is-ancestor`, but it didn't help.)
    #   - Then we updated to just comparing the commit date. I think it might make less sense than checking ancestry, and might lead to wrong results, maybe? But currently it seems to work okay and is faster. 
    #   - Not sure if `committed_date` or `authored_date` is better. Both seem to give the same results atm.
        
    return potential_predecessor_commit.committed_date <= commit.committed_date
    # return runCLT(f"git rev-list --is-ancestor {potential_predecessor_commit.hexsha} {commit.hexsha}").returncode == 0
    # return runCLT(f"git merge-base --is-ancestor {potential_predecessor_commit.hexsha} {commit.hexsha}").returncode == 0

def runCLT(command):
    clt_result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) # Not sure what `text` and `shell` does.
    return clt_result

#
# Find files
#

def find_localization_files_in_mmf_repo(repo_root):
    
    """
    Find localization files
    
    Structure of the result:
    [
        {  
            base: path_to_base_localization_file, 
            basetype: "<IB | strings | markdown>"", 
            translations: {
                path_to_translated_file1: {}, 
                path_to_translated_file2: {}, 
                ...
            } 
        },
        ...
    ]
    """
    
    # Constants
    
    markdown_dir = repo_root + '/' + "Markdown/Templates"
    exclude_paths_relative = ["Frameworks/Sparkle.framework"]
    exclude_paths = list(map(lambda exc: repo_root + '/' + exc, exclude_paths_relative))
    
    # Get result
        
    result = []
    
    # Find base_files
    
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [d for d in dirs if root + '/' + d not in exclude_paths]
        is_en_folder = 'en.lproj' in os.path.basename(root)
        is_base_folder = 'Base.lproj' in os.path.basename(root)
        if is_base_folder or is_en_folder:
            files_absolute = map(lambda file: root + '/' + file, files)
            for b in files_absolute:
                # Validate
                _, extension = os.path.splitext(b)
                assert(is_en_folder or is_base_folder)
                if is_en_folder: assert extension in ['.strings', '.stringsdict'], f"en.lproj folder contained file with extension {extension}"
                if is_base_folder: assert extension in ['.xib', '.storyboard'], f"Base.lproj folder contained file with extension {extension}"
                # Get type
                type = 'strings' if is_en_folder else 'IB'
                # Append
                result.append({ 'base': b, 'basetype': type })
    
    for root, dirs, files in os.walk(markdown_dir):
        is_en_folder = 'en-US' in os.path.basename(root)
        if is_en_folder:
            files_absolute = map(lambda file: root + '/' + file, files)
            for b in files_absolute:
                # Append
                result.append({ 'base': b, 'basetype': 'markdown' })
    
    # Find translated files
    
    for e in result:
        
        base_path = e['base']
        basetype = e['basetype']
        
        translations = {}
        
        # Get grandparent dir of the base file, which contains all the translation files
        grandpa = os.path.dirname(os.path.dirname(base_path))
        
        for root, dirs, files in os.walk(grandpa):
            
            if basetype == 'IB' or basetype == 'strings':
                
                # Don't go into .lproj folders
                dirs[:] = [d for d in dirs if '.lproj' in d]
                
                # Only process files inside ``.lproj`` folders
                if not '.lproj' in os.path.basename(root):
                    continue
            
            
            # Process files
            for f in files:
                
                # Get filenames and extensions
                filename, extension = os.path.splitext(os.path.basename(f))
                base_filename, base_extension = os.path.splitext(os.path.basename(base_path))
                
                # Get other
                absolute_f = root + '/' + f
                
                # Combine info
                filename_matches = filename == base_filename
                extension_matches = extension == base_extension
                is_base_file = absolute_f == base_path
                
                # Append
                if  not is_base_file and filename_matches:
                    if basetype == 'markdown':
                        translations[absolute_f] = {}
                    elif basetype == 'IB':
                        translations[absolute_f] = {}
                    elif basetype == 'strings':
                        if extension_matches:
                            translations[absolute_f] = {}
                    else:
                        assert False
        
        # Append
        e['translations'] = translations
    
    return result

#
# Call main
#
if __name__ == "__main__": 
    main()