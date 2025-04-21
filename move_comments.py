import re

def move_comments(input_path, output_path):
    with open(input_path, 'r') as infile, open(output_path, 'w') as outfile:
        prev_line = ''
        
        for line in infile:
            line = line.rstrip('\n')
            if line.strip().startswith('<!--'):
                comment = line.strip()
                if prev_line:
                    outfile.write(prev_line.rstrip() + ' ' + comment + '\n')
                    prev_line = ''
            else:
                if prev_line:
                    outfile.write(prev_line + '\n')
                prev_line = line
        if prev_line:
            outfile.write(prev_line + '\n')


if __name__ == "__main__":
    import os

    cwd = os.path.dirname(__file__)
    move_comments(os.path.join(cwd, "c0000.xml"), os.path.join(cwd, "c0000_out.xml"))
