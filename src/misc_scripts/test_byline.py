import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from src.preprocessing.by_line_dataset import by_line_dataset
dataset = by_line_dataset(max_lines=50, max_line_length=120, batch_size=64, binary_encoding=False)
train, val = dataset.get_dataset()

for batch in train:
	print("batch"+str(batch)
